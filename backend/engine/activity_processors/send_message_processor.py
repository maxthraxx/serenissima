import logging
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from pyairtable import Table
from backend.engine.utils.activity_helpers import (
    _escape_airtable_value, 
    VENICE_TIMEZONE,
    find_path_between_buildings,
    get_building_record,
    get_citizen_record
)
from backend.engine.utils.conversation_helper import generate_conversation_turn
from backend.engine.utils.notification_helpers import create_notification
import os # For KINOS_API_KEY

log = logging.getLogger(__name__)

def process_send_message_fn(
    tables: Dict[str, Any],
    activity_record: Dict[str, Any],
    building_type_defs: Any,
    resource_defs: Any,
    api_base_url: Optional[str] = None # Added api_base_url for signature consistency
) -> bool:
    """
    Process activities in the send_message chain.
    
    This processor handles:
    1. goto_location - When citizen arrives at the receiver's location or meeting place (no action needed)
    2. deliver_message_interaction - Process the message delivery and create the message record
    3. send_message - Direct message sending without physical interaction (for system messages, etc.)
    """
    fields = activity_record.get('fields', {})
    activity_type = fields.get('Type')
    citizen = fields.get('Citizen')
    notes_str = fields.get('Notes') # Changed Details to Notes
    
    try:
        details = json.loads(notes_str) if notes_str else {} # Changed details_str to notes_str
    except Exception as e:
        log.error(f"Error parsing Notes for {activity_type}: {e}") # Changed Details to Notes
        return False
    
    # Handle goto_location activity (first step in chain)
    if activity_type == "goto_location" and details.get("activityType") == "send_message":
        # No need to create the deliver_message_interaction activity as it's already created
        # Just log and return success
        log.info(f"Citizen {citizen} has arrived at the location to deliver a message to {details.get('receiverUsername')}.")
        log.info(f"The deliver_message_interaction activity should already be scheduled to start after this activity.")
        return True
    
    # Handle deliver_message_interaction activity (second step in chain)
    elif activity_type == "deliver_message_interaction":
        # api_base_url is required by generate_conversation_turn
        if not api_base_url:
            log.error("api_base_url is required for deliver_message_interaction but not provided.")
            return False
        return _process_message_delivery(tables, activity_record, details, api_base_url)
    
    # Handle direct send_message activity (no physical interaction required)
    elif activity_type == "send_message":
        return _process_direct_message(tables, activity_record, details)
    
    else:
        log.error(f"Unexpected activity type in send_message processor: {activity_type}")
        return False

def _process_direct_message(
    tables: Dict[str, Any],
    activity_record: Dict[str, Any],
    details: Dict[str, Any]
) -> bool:
    """Process a direct message send without physical interaction."""
    fields = activity_record.get('fields', {})
    sender = fields.get('Citizen')
    receiver_username = details.get('receiverUsername')
    content = details.get('content')
    message_type = details.get('messageType', 'message')
    in_reply_to = details.get('inReplyToMessageId')
    channel = details.get('channel') # Extract channel
    add_message = details.get('addMessage') # Extract addMessage if present
    
    if not (sender and receiver_username and content):
        log.error(f"Missing data for direct message: sender={sender}, receiver={receiver_username}, content={'present' if content else 'missing'}")
        return False
    
    try:
        # Create a message ID
        message_id = f"msg_{sender}_{receiver_username}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        
        # Create the message record
        message_fields = {
            "MessageId": message_id,
            "Sender": sender,
            "Receiver": receiver_username,
            "Content": content,
            "Type": message_type,
            "CreatedAt": datetime.now(timezone.utc).isoformat(),
            "ReadAt": None # Mark as unread initially
        }
        
        # Add Notes if this is a reply
        if in_reply_to:
            message_fields["Notes"] = f"In reply to: {in_reply_to}"
        
        if channel:
            message_fields["Channel"] = channel
            
        created_message_record = tables["messages"].create(message_fields)
        log.info(f"Created direct message from {sender} to {receiver_username} with ID: {created_message_record['id']} (Custom MessageId: {message_id}). Channel: {channel or 'N/A'}")
        
        # Create a notification for the receiver
        notification_fields = {
            "Citizen": receiver_username,
            "Type": "message_received",
            "Content": f"You have received a {message_type} message from {sender}.",
            "Details": json.dumps({
                "messageId": message_id,
                "sender": sender,
                "messageType": message_type,
                "preview": content[:50] + ("..." if len(content) > 50 else "")
            }),
            "Asset": message_id,
            "AssetType": "message",
            "Status": "unread",
            "CreatedAt": datetime.now(timezone.utc).isoformat()
        }
        
        tables["notifications"].create(notification_fields)
        log.info(f"Created notification for {receiver_username} about message from {sender}")
        
        # Check if a relationship exists between sender and receiver
        relationship_formula = f"OR(AND({{Citizen1}}='{_escape_airtable_value(sender)}', {{Citizen2}}='{_escape_airtable_value(receiver_username)}'), AND({{Citizen1}}='{_escape_airtable_value(receiver_username)}', {{Citizen2}}='{_escape_airtable_value(sender)}'))"
        relationship_records = tables["relationships"].all(formula=relationship_formula, max_records=1)
        
        if relationship_records:
            # Update existing relationship
            relationship_record = relationship_records[0]
            relationship_id = relationship_record['id']
            
            # Update LastInteraction and potentially strengthen the relationship
            current_strength = float(relationship_record['fields'].get('StrengthScore', 0))
            new_strength = min(100, current_strength + 2)  # Increment by 2, max 100
            
            tables["relationships"].update(relationship_id, {
                'LastInteraction': datetime.now(timezone.utc).isoformat(),
                'StrengthScore': new_strength
            })
            
            log.info(f"Updated relationship between {sender} and {receiver_username}. New strength: {new_strength}")
        else:
            # Create new relationship
            # Ensure citizens are in alphabetical order for Citizen1 and Citizen2
            if sender < receiver_username:
                citizen1 = sender
                citizen2 = receiver_username
            else:
                citizen1 = receiver_username
                citizen2 = sender
            
            relationship_id = f"rel_{citizen1}_{citizen2}"
            
            relationship_fields = {
                "RelationshipId": relationship_id,
                "Citizen1": citizen1,
                "Citizen2": citizen2,
                "Title": "Acquaintance",  # Default relationship type
                "Description": f"Initial contact established when {sender} sent a message to {receiver_username}.",
                "LastInteraction": datetime.now(timezone.utc).isoformat(),
                "Tier": 1,  # Initial tier
                "Status": "active",
                "StrengthScore": 10,  # Initial strength
                "TrustScore": 5,  # Initial trust
                "CreatedAt": datetime.now(timezone.utc).isoformat()
            }
            
            tables["relationships"].create(relationship_fields)
            log.info(f"Created new relationship between {sender} and {receiver_username}")
        
        return True
    except Exception as e:
        log.error(f"Failed to process direct message: {e}")
        import traceback
        log.error(traceback.format_exc())
        return False

def _process_message_delivery(
    tables: Dict[str, Any],
    message_activity: Dict[str, Any],
    details: Dict[str, Any],
    api_base_url: str # Added api_base_url
) -> bool:
    """Process the message delivery when the deliver_message_interaction activity is executed."""
    fields = message_activity.get('fields', {})
    kinos_api_key = os.getenv("KINOS_API_KEY")
    if not kinos_api_key:
        log.error("KINOS_API_KEY not found in environment variables. Cannot proceed with message delivery.")
        return False
        
    sender = fields.get('Citizen')
    receiver_username = details.get('receiverUsername')
    content = details.get('content')
    message_type = details.get('messageType', 'personal')
    in_reply_to_id = details.get('inReplyToMessageId') # Extract from parsed Details
    channel = details.get('channel') # Extract channel
    target_citizen_username_for_trust_impact = details.get('targetCitizenUsernameForTrustImpact') # New
    add_message = details.get('addMessage') # Extract addMessage if present
    
    if not (sender and receiver_username and content):
        log.error(f"Missing data for message delivery: sender={sender}, receiver={receiver_username}, content={'present' if content else 'missing'}")
        return False
    
    # Verify the receiver exists
    receiver_formula = f"{{Username}}='{_escape_airtable_value(receiver_username)}'"
    receiver_records = tables["citizens"].all(formula=receiver_formula, max_records=1)
    
    if not receiver_records:
        log.error(f"Receiver {receiver_username} not found")
        return False
    
    receiver_record = receiver_records[0]
    
    try:
        # 1. Generate conversation opener using the conversation helper
        log.info(f"Calling generate_conversation_turn for {sender} to {receiver_username} with original content.")
        new_message_airtable_record = generate_conversation_turn(
            tables=tables,
            kinos_api_key=kinos_api_key,
            speaker_username=sender,
            listener_username=receiver_username,
            api_base_url=api_base_url,
            interaction_mode="conversation_opener",
            message=add_message.get("customPrompt") if add_message and add_message.get("generateMessageOnDelivery") else content, # Use customPrompt if available
            target_citizen_username_for_trust_impact=target_citizen_username_for_trust_impact, # New
            add_message=add_message # Pass addMessage to conversation helper
        )

        if not new_message_airtable_record or 'fields' not in new_message_airtable_record:
            log.error(f"Failed to generate or persist conversation opener message from {sender} to {receiver_username}.")
            return False

        message_id = new_message_airtable_record['fields'].get('MessageId')
        actual_content_stored = new_message_airtable_record['fields'].get('Content', content) # Fallback to original content if not in record
        
        if not message_id:
            log.error(f"Conversation helper did not return a MessageId for the message from {sender} to {receiver_username}.")
            return False
            
        log.info(f"Message from {sender} to {receiver_username} (Type: {message_type}, Channel: {channel or 'N/A'}) processed by conversation helper. New MessageId: {message_id}")

        # 2. Check if a relationship exists between sender and receiver
        relationship_formula = f"OR(AND({{Citizen1}}='{_escape_airtable_value(sender)}', {{Citizen2}}='{_escape_airtable_value(receiver_username)}'), AND({{Citizen1}}='{_escape_airtable_value(receiver_username)}', {{Citizen2}}='{_escape_airtable_value(sender)}'))"
        relationship_records = tables["relationships"].all(formula=relationship_formula, max_records=1)
        
        if relationship_records:
            # Update existing relationship
            relationship_record = relationship_records[0]
            relationship_id = relationship_record['id']
            
            # Update LastInteraction and potentially strengthen the relationship
            current_strength = float(relationship_record['fields'].get('StrengthScore', 0))
            new_strength = min(100, current_strength + 2)  # Increment by 2, max 100
            
            tables["relationships"].update(relationship_id, {
                'LastInteraction': datetime.now(timezone.utc).isoformat(),
                'StrengthScore': new_strength
            })
            
            log.info(f"Updated relationship between {sender} and {receiver_username}. New strength: {new_strength}")
        else:
            # Create new relationship
            # Ensure citizens are in alphabetical order for Citizen1 and Citizen2
            if sender < receiver_username:
                citizen1 = sender
                citizen2 = receiver_username
            else:
                citizen1 = receiver_username
                citizen2 = sender
            
            relationship_id = f"rel_{citizen1}_{citizen2}"
            
            relationship_fields = {
                "RelationshipId": relationship_id,
                "Citizen1": citizen1,
                "Citizen2": citizen2,
                "Title": "Acquaintance",  # Default relationship type
                "Description": f"Initial contact established when {sender} sent a message to {receiver_username}.",
                "LastInteraction": datetime.now(timezone.utc).isoformat(),
                "Tier": 1,  # Initial tier
                "Status": "active",
                "StrengthScore": 10,  # Initial strength
                "TrustScore": 5,  # Initial trust
                "CreatedAt": datetime.now(timezone.utc).isoformat()
            }
            
            tables["relationships"].create(relationship_fields)
            
            log.info(f"Created new relationship between {sender} and {receiver_username}")
        
        # 3. Create a notification for the receiver using the helper
        notification_content = f"You have received a {message_type} message from {sender}."
        notification_details = {
            "messageId": message_id,
            "sender": sender,
            "messageType": message_type, # Use the original message_type for the notification
            "preview": actual_content_stored[:50] + ("..." if len(actual_content_stored) > 50 else "")
        }
        create_notification(
            tables=tables,
            citizen_username=receiver_username,
            notification_type="message_received",
            content=notification_content,
            details=notification_details,
            asset_id=message_id,
            asset_type="message"
        )
        log.info(f"Notification created for {receiver_username} regarding message {message_id} from {sender}.")
        
        # 4. Create a reply_to_message activity for the receiver
        # Get current position of the receiver
        receiver_position_str = receiver_record['fields'].get('Position')
        current_position = None
        if receiver_position_str:
            try:
                current_position = json.loads(receiver_position_str)
            except json.JSONDecodeError:
                log.warning(f"Could not parse receiver position: {receiver_position_str}")
        
        # Get the sender's current position (which should be where the message was delivered)
        from_building_id = fields.get('FromBuilding')
        
        # Create a timestamp for the activity IDs
        ts = int(datetime.now(VENICE_TIMEZONE).timestamp())
        
        # Create the reply activity ID
        reply_activity_id = f"reply_to_message_{receiver_username}_{sender}_{ts}"
        
        # Set the activity to start in 10 minutes and last for 10 minutes
        now_utc = datetime.now(timezone.utc)
        reply_start_date = (now_utc + timedelta(minutes=10)).isoformat()
        reply_end_date = (now_utc + timedelta(minutes=20)).isoformat()
        
        # Create the reply_to_message activity
        reply_payload = {
            "ActivityId": reply_activity_id,
            "Type": "reply_to_message",
            "Citizen": receiver_username,
            "FromBuilding": from_building_id,  # Start from where the message was delivered
            "ToBuilding": from_building_id,    # Reply at the same location
            "Details": json.dumps({
                "originalMessageId": message_id,
                "receiverUsername": sender,  # The original sender becomes the receiver of the reply
                "messageType": message_type,
                "conversationLength": 3  # Default to 3 exchanges in the conversation
            }),
            "Status": "created",
            "Title": f"Replying to message from {sender}",
            "Description": f"Preparing a reply to the {message_type} message from {sender}",
            "Notes": f"Automatically created reply activity in response to message {message_id}",
            "CreatedAt": datetime.now(timezone.utc).isoformat(),
            "StartDate": reply_start_date,
            "EndDate": reply_end_date,
            "Priority": 30  # Medium priority for social activities
        }
        
        tables["activities"].create(reply_payload)
        log.info(f"Created reply_to_message activity {reply_activity_id} for {receiver_username} to respond to {sender}")
        
        log.info(f"Successfully delivered message from {sender} to {receiver_username}")
        log.info(f"Created message record with ID: {message_id}")
        
        return True
    except Exception as e:
        log.error(f"Failed to process message delivery: {e}")
        import traceback
        log.error(traceback.format_exc())
        return False
