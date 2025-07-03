# This file makes the 'activity_creators' directory a Python package.

# Optionally, you can import key functions here for easier access, e.g.:
from .stay_activity_creator import try_create as try_create_stay_activity
from .goto_work_activity_creator import try_create as try_create_goto_work_activity
from .goto_home_activity_creator import try_create as try_create_goto_home_activity
from .travel_to_inn_activity_creator import try_create as try_create_travel_to_inn_activity
from .idle_activity_creator import try_create as try_create_idle_activity
from .production_activity_creator import try_create as try_create_production_activity
from .resource_fetching_activity_creator import try_create as try_create_resource_fetching_activity
from .eat_activity_creator import (
    try_create_eat_from_inventory_activity,
    try_create_eat_at_home_activity,
    try_create_eat_at_tavern_activity
)
from .fetch_from_galley_activity_creator import try_create as try_create_fetch_from_galley_activity
# bid_on_land_activity_creator is removed as it's redundant with make_offer_for_land_creator
from .leave_venice_activity_creator import try_create as try_create_leave_venice_activity
from .manage_public_dock_activity_creator import try_create as try_create_manage_public_dock_activity # Import for manage_public_dock
from .deliver_construction_materials_creator import try_create_deliver_construction_materials_activity
from .construct_building_creator import try_create_construct_building_activity
from .secure_warehouse_activity_creator import try_create as try_create_secure_warehouse_activity
from .deliver_to_storage_activity_creator import try_create as try_create_deliver_to_storage_activity
from .fetch_from_storage_activity_creator import try_create as try_create_fetch_from_storage_activity
from .fetch_for_logistics_client_activity_creator import try_create as try_create_fetch_for_logistics_client_activity # Already present
from .check_business_status_activity_creator import try_create as try_create_check_business_status_activity
from .fishing_activity_creator import try_create_fishing_activity # Fishing activity creator
from .return_to_workplace_activity_creator import try_create as try_create_return_to_workplace_activity # New
from .manage_public_sell_contract_creator import try_create as try_create_manage_public_sell_contract_activity # New public sell contract activity
from .manage_import_contract_creator import try_create as try_create_manage_import_contract_activity # New import contract activity
from .manage_public_import_contract_creator import try_create as try_create_manage_public_import_contract_activity # New public import contract activity
from .manage_logistics_service_contract_creator import try_create as try_create_manage_logistics_service_contract_activity # New logistics service contract activity
from .buy_available_land_creator import try_create as try_create_buy_available_land_activity # New land purchase activity
from .initiate_building_project_creator import try_create_smart_wrapper as try_create_initiate_building_project_activity # Smart wrapper that handles both old and new signatures
from .adjust_land_lease_price_creator import try_create as try_create_adjust_land_lease_price_activity # New land lease price adjustment activity
from .adjust_building_rent_price_creator import try_create as try_create_adjust_building_rent_price_activity # New building rent price adjustment activity
from .adjust_business_wages_creator import try_create as try_create_adjust_business_wages_activity # New business wages adjustment activity
from .adjust_building_lease_price_creator import try_create as try_create_adjust_building_lease_price_activity # New building lease price adjustment activity
from .change_business_manager_creator import try_create as try_create_change_business_manager_activity # New business manager change activity
from .request_loan_creator import try_create as try_create_request_loan_activity # New loan request activity
from .offer_loan_creator import try_create as try_create_offer_loan_activity # New loan offer activity
from .send_message_creator import try_create as try_create_send_message_activity # New message sending activity
from .manage_guild_membership_creator import try_create as try_create_manage_guild_membership_activity # New guild membership activity
from .bid_on_building_activity_creator import try_create as try_create_bid_on_building_activity # New building bid activity
from .deliver_resource_batch_activity_creator import try_create as try_create_deliver_resource_batch_activity # New, for galley final deliveries

# Land Management Activity Creators
# Note: bid_on_land_activity_creator.py was removed. make_offer_for_land_creator.py is used instead.
from .list_land_for_sale_creator import try_create as try_create_list_land_for_sale_activity
from .make_offer_for_land_creator import try_create as try_create_make_offer_for_land_activity
from .accept_land_offer_creator import try_create as try_create_accept_land_offer_activity
from .buy_listed_land_creator import try_create as try_create_buy_listed_land_activity
from .cancel_land_listing_creator import try_create as try_create_cancel_land_listing_activity
from .cancel_land_offer_creator import try_create as try_create_cancel_land_offer_activity
# Note: buy_available_land_creator already exists and is imported

# Import new stubbed creators
from .respond_to_building_bid_creator import try_create as try_create_respond_to_building_bid_activity
from .withdraw_building_bid_creator import try_create as try_create_withdraw_building_bid_activity
from .manage_markup_buy_contract_creator import try_create as try_create_manage_markup_buy_contract_activity
from .manage_storage_query_contract_creator import try_create as try_create_manage_storage_query_contract_activity
from .manage_public_storage_offer_creator import try_create as try_create_manage_public_storage_offer_activity
from .update_citizen_profile_creator import try_create as try_create_update_citizen_profile_activity
from .work_on_art_creator import try_create_work_on_art_activity # Import for Artisti work
from .read_book_activity_creator import try_create_read_book_activity # Import for reading books
from .attend_theater_performance_creator import try_create_attend_theater_performance_activity # New theater activity
from .drink_at_inn_activity_creator import try_create_drink_at_inn_activity # New drink at inn activity
from .use_public_bath_creator import try_create_use_public_bath_activity # New public bath activity
from .goto_location_activity_creator import try_create as try_create_goto_location_activity # Assuming file is goto_location_activity_creator.py
from .deposit_inventory_orchestrator_creator import try_create_deposit_inventory_orchestrator # New orchestrator
from .attend_mass_creator import try_create_attend_mass_activity, find_nearest_church # New mass attendance activity
from .prepare_sermon_creator import try_create_prepare_sermon_activity # New sermon preparation activity for Clero
from .study_literature_activity_creator import try_create as try_create_study_literature_activity # New scientific study activity for Scientisti
from .spread_rumor_activity_creator import try_create as try_create_spread_rumor_activity # Rumor spreading activity
from .observe_phenomena_activity_creator import try_create as try_create_observe_phenomena_activity # Scientific observation activity
from .goto_position_activity_creator import try_create as try_create_goto_position_activity # Movement to specific coordinates
from .research_investigation_activity_creator import try_create as try_create_research_investigation_activity # Deep research with Claude consultation
from .pray_activity_creator import try_create_pray_activity, find_nearest_church as find_nearest_church_for_prayer # Prayer activity
from .research_scope_definition_activity_creator import try_create as try_create_research_scope_definition_activity # Research planning for Scientisti
from .hypothesis_and_question_development_activity_creator import try_create as try_create_hypothesis_and_question_development_activity # Hypothesis formation for Scientisti
from .knowledge_integration_activity_creator import try_create as try_create_knowledge_integration_activity # Knowledge synthesis for Scientisti

# Innovatori activity creators
from .observe_system_patterns_activity_creator import try_create as try_create_observe_system_patterns_activity
from .interview_citizens_activity_creator import try_create as try_create_interview_citizens_activity
from .build_prototype_activity_creator import try_create as try_create_build_prototype_activity
from .test_innovation_activity_creator import try_create as try_create_test_innovation_activity
from .draft_blueprint_activity_creator import try_create as try_create_draft_blueprint_activity
from .present_innovation_activity_creator import try_create as try_create_present_innovation_activity
from .talk_publicly_activity_creator import try_create as try_create_talk_publicly_activity # Public announcement activity
from .send_diplomatic_email_creator import try_create_send_diplomatic_email_activity # Diplomatic email activity
