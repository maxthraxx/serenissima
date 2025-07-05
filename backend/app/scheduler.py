import os
import sys
import time
import threading # Import threading
import argparse # Added for command-line arguments
import pytz # Added for timezone.utc if needed, and consistent with VENICE_TIMEZONE
import json # Added for problem creation

# Add project root to sys.path for consistent imports
PROJECT_ROOT_SCHEDULER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT_SCHEDULER not in sys.path:
    sys.path.insert(0, PROJECT_ROOT_SCHEDULER)

# Define scripts that should respect the --hour override at module level
SCRIPTS_RESPECTING_FORCED_HOUR = [
    "engine/createActivities.py",
    "engine/processActivities.py",
    "engine/createimportactivities.py", # Added this as it now supports --hour
    "engine/createmarketgalley.py", # Added for market galley creation
    "relevancies/gatherInformation.py", # Added for intelligence gathering
    "engine/processStratagems.py", # Ajout du processeur de stratagèmes
    "reports/createReports.py", # Added for Renaissance reports generation
    "engine/emergency_food_distribution_charity_contracts.py", # Charity contract-based emergency food distribution
    "engine/daily/gradient_mill_production.py" # Automated mill production processing
    # Add other scripts here if they are updated to support --hour
]
import subprocess
from datetime import datetime, timedelta, timezone # Added timezone for timezone.utc
from colorama import Fore, Style # Added import for colorama
from typing import Dict, Optional # Import Dict and Optional for type hinting
import requests # Added for Telegram notifications
from pyairtable import Table # Added for problem creation
from dotenv import load_dotenv # Added for environment variables

# Load environment variables
load_dotenv()

def run_scheduled_tasks(forced_hour: Optional[int] = None): # Added forced_hour parameter
    """Run scheduled tasks at specific times."""
    # VENICE_TIMEZONE should be available if createActivities.py or similar context is loaded.
    # For robustness, define it here or ensure it's imported.
    from backend.engine.utils.activity_helpers import VENICE_TIMEZONE
    print(f"Scheduler: VENICE_TIMEZONE imported successfully: {VENICE_TIMEZONE}")

    active_threads: Dict[str, threading.Thread] = {} # To keep track of active frequent task threads

    while True:
        real_now_utc = datetime.now(timezone.utc) # Use timezone-aware UTC now
        real_now_venice = real_now_utc.astimezone(VENICE_TIMEZONE)

        if forced_hour is not None:
            # Override the hour component, keep other components from real_now_venice
            now_venice = real_now_venice.replace(hour=forced_hour)
            # Derive now_utc from the potentially modified now_venice
            now_utc = now_venice.astimezone(pytz.UTC) # Ensure now_utc is UTC
            print(f"{Fore.YELLOW}Scheduler: Using FORCED Venice hour: {forced_hour}. Effective now_venice: {now_venice.isoformat()}, Effective now_utc: {now_utc.isoformat()}{Style.RESET_ALL}")
        else:
            now_venice = real_now_venice
            now_utc = real_now_utc
        
        # current_hour_utc and current_minute_utc for frequent tasks should reflect the true passage of minutes.
        # If we want frequent tasks to also operate under the "forced time illusion" for their minute component,
        # then current_minute_utc should be derived from now_utc (which is based on forced now_venice).
        # If we want frequent tasks to run on real UTC minutes, use real_now_utc.minute.
        # For consistency with the forced hour affecting the "game time", let's use the derived now_utc.
        current_hour_utc = now_utc.hour 
        current_minute_utc = now_utc.minute

        current_hour_venice = now_venice.hour 
        current_minute_venice = now_venice.minute

        # Get the absolute path to the backend directory once
        backend_dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # --- Define a wrapper function for threaded task execution ---
        def run_task_in_thread(script_path_relative: str, task_name: str, active_threads_dict: Dict[str, threading.Thread], scheduler_forced_hour: Optional[int]): # Added scheduler_forced_hour
            script_full_path = os.path.join(backend_dir_path, script_path_relative)
            command_parts = ["python3", script_full_path] # Basic command

            # Handle potential arguments in script_path_relative (e.g., "script.py --arg value")
            actual_script_to_check = script_path_relative # Path for checking against scripts_respecting_forced_hour
            if " " in script_path_relative:
                parts = script_path_relative.split(" ", 1)
                actual_script_relative_path = parts[0]
                script_args = parts[1].split()
                script_full_path = os.path.join(backend_dir_path, actual_script_relative_path)
                command_parts = ["python3", script_full_path] + script_args
                actual_script_to_check = actual_script_relative_path # Update for checking
            
            # Propagate forced_hour if set for the scheduler AND if the script is one that should respect it
            if scheduler_forced_hour is not None and actual_script_to_check in SCRIPTS_RESPECTING_FORCED_HOUR: # Use module-level constant
                command_parts.extend(["--hour", str(scheduler_forced_hour)])

            print(f"Scheduler (Thread {threading.get_ident()}): Starting task: {task_name} with command: {' '.join(command_parts)}")
            try:
                output_lines = []
                process = subprocess.Popen(
                    command_parts,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    cwd=backend_dir_path  # Set working directory to backend
                )
                if process.stdout:
                    for line in iter(process.stdout.readline, ''):
                        stripped_line = line.strip()
                        print(f"[{task_name} - Thread {threading.get_ident()}] {stripped_line}")
                        output_lines.append(stripped_line)
                    process.stdout.close()
                
                return_code = process.wait()
                log_output_for_telegram = "\n".join(output_lines[-20:]) # Get last 20 lines for notification

                if return_code == 0:
                    print(f"Scheduler (Thread {threading.get_ident()}): Successfully ran {task_name}")
                else:
                    error_message = f"Scheduler (Thread {threading.get_ident()}): Error running {task_name}. Return code: {return_code}"
                    print(error_message)
                    if "KeyboardInterrupt" not in log_output_for_telegram:
                        telegram_message = (f"[X] Task Failed: {task_name}\n" # Replaced ❌
                                            f"Script: `{script_full_path}`\n"
                                            f"Return Code: {return_code}\n\n"
                                            f"```\n--- Last 20 lines of log ---\n{log_output_for_telegram}\n```")
                        send_telegram_notification(telegram_message)
                        # Create problem record for 5-minute task failure
                        create_scheduler_problem(task_name, script_full_path, 
                                               f"Task failed with return code: {return_code}", 
                                               log_output_for_telegram)
                    else:
                        print(f"Scheduler (Thread {threading.get_ident()}): KeyboardInterrupt detected for {task_name}. Skipping Telegram notification.")
            except FileNotFoundError:
                error_message = f"Scheduler (Thread {threading.get_ident()}): Exception running {task_name}: Script not found at {script_full_path}"
                print(error_message)
                # No specific log output to check for KeyboardInterrupt here, but FileNotFoundError is unlikely to be a KeyboardInterrupt scenario.
                send_telegram_notification(f"[X] Task Failed: {task_name}\nScript: `{script_full_path}`\nError: Script not found") # Replaced ❌
                # Create problem record for missing script
                create_scheduler_problem(task_name, script_full_path, 
                                       "Script file not found", 
                                       "The specified script does not exist at the expected path.")
            except Exception as e:
                error_message = f"Scheduler (Thread {threading.get_ident()}): Exception running {task_name}: {str(e)}"
                print(error_message)
                log_output_for_telegram_exception = "\n".join(output_lines[-20:]) if output_lines else "No specific script output captured before exception."
                if "KeyboardInterrupt" not in str(e) and "KeyboardInterrupt" not in log_output_for_telegram_exception:
                    telegram_message = (f"[X] Task Failed: {task_name}\n" # Replaced ❌
                                        f"Script: `{script_full_path}`\n"
                                        f"Exception: {str(e)}\n\n"
                                        f"```\n--- Last 20 lines of log (if any) ---\n{log_output_for_telegram_exception}\n```")
                    send_telegram_notification(telegram_message)
                    # Create problem record for exception
                    create_scheduler_problem(task_name, script_full_path, 
                                           f"Exception: {str(e)}", 
                                           log_output_for_telegram_exception)
                else:
                    print(f"Scheduler (Thread {threading.get_ident()}): KeyboardInterrupt detected during exception for {task_name}. Skipping Telegram notification.")
            finally:
                # Remove from active threads when done
                if task_name in active_threads_dict:
                    del active_threads_dict[task_name]
                print(f"Scheduler (Thread {threading.get_ident()}): Task {task_name} finished and removed from active_threads.")

        # --- Frequent tasks (every 5 minutes) ---
        frequent_tasks_definitions = [
            {"minute_mod": 0, "script": "engine/createActivities.py", "name": "Citizen activity creation", "interval_minutes": 5},
            # {"minute_mod": 1, "script": "resources/processdecay.py", "name": "Resource decay processing", "interval_minutes": 20},
            {"minute_mod": 2, "script": "engine/processActivities.py", "name": "Process concluded activities", "interval_minutes": 5},
            {"minute_mod": 3, "script": "engine/delivery_retry_handler.py", "name": "Delivery retry handler", "interval_minutes": 15},
            {"minute_mod": 4, "script": "forge-communication/forge_message_processor.py", "name": "Forge message check", "interval_minutes": 5},
        ]

        for task_def in frequent_tasks_definitions:
            task_interval = task_def.get("interval_minutes", 5) # Default to 5 if not specified
            if (current_minute_utc - task_def["minute_mod"]) % task_interval == 0:
                task_name = task_def["name"]
                if task_name not in active_threads or not active_threads[task_name].is_alive():
                    print(f"Scheduler: Time for {task_interval}-minute task ({task_name}) at {now_utc.isoformat()} UTC. Launching in new thread.")
                    thread = threading.Thread(target=run_task_in_thread, args=(task_def["script"], task_name, active_threads, forced_hour)) # Pass forced_hour
                    thread.daemon = True  # Set worker thread as daemon
                    active_threads[task_name] = thread
                    thread.start()
                else:
                    print(f"Scheduler: Task {task_name} is already running. Skipping new launch at {now_utc.isoformat()} UTC.")
        
        # Hourly tasks (check only at the top of the hour in Venice time)
        # These will still run sequentially and block the main scheduler loop while they execute.
        if current_minute_venice == 0:
            print(f"Scheduler checking for hourly tasks at {now_venice.isoformat()} Venice Time (UTC: {now_utc.isoformat()})")
            
            # Map of hours (Venice Time) to lists of tasks. 
            # Each task is a tuple (script_path, task_name, target_minute_of_hour).
            # Comments indicate Venice Time (VT).
            # Tasks are staggered to avoid simultaneous execution at the top of the hour.
            tasks = {
                7: [("engine/createimportactivities.py", "Process resource imports (Morning)", 0), # 7:00 VT
                    ("engine/pay_building_maintenance.py", "Building maintenance collection", 5), # 7:05 VT
                    ("ais/generatethoughts.py --model local", "AI Thought Generation", 10)], # 7:10 VT
                5: [("ais/automated_adjustimports.py", "Automated AI Import Contract Creation", 0), # 5:00 VT
                    ("ais/automated_adjustmarkupbuys.py", "Automated Markup Buys", 5), # 5:05 VT
                    ("relevancies/gatherInformation.py", "Daily Intelligence Report Generation", 10), # 5:10 VT
                    ("engine/daily/gradient_mill_production.py", "Automated Mill Production Processing", 20)], # 5:20 VT
                6: [("ais/answertomessages.py --model local", "AI message responses", 0)], # 6:00 VT
                8: [("engine/treasuryRedistribution.py", "Treasury redistribution", 0), # 8:00 VT
                    ("ais/answertomessages.py --model local", "AI message responses", 5), # 8:05 VT
                    ("engine/createmarketgalley.py --food", "Create Market Galley (Food)", 10)], # 8:10 VT
                9: [("engine/distributeLeases.py", "Lease distribution", 0), # 9:00 VT
                    ("ais/autoResolveProblems.py", "Auto Resolve Problems (Morning)", 45)], # 9:45 VT
                10: [("engine/citizensgetjobs_proximity.py", "Proximity-based job assignment", 0), # 10:00 VT
                     ("ais/answertomessages.py --model local", "AI message responses", 5)], # 10:05 VT
                11: [("engine/immigration.py", "Immigration", 0), # 11:00 VT
                     ("engine/processStratagems.py", "Process Active Stratagems (Mid-day)", 5)], # 11:05 VT
                12: [("engine/househomelesscitizens.py", "Housing homeless citizens", 0), # 12:00 VT
                     ("ais/answertomessages.py --model local", "AI message responses", 5)], # 12:05 VT
                13: [("engine/createimportactivities.py", "Process resource imports (Afternoon)", 0), # 13:00 VT
                     ("engine/decrees/affectpublicbuildingstolandowners.py", "Public buildings assignment", 5), # 13:05 VT
                     ("engine/updateSocialClass.py", "Social class updates", 10), # 13:10 VT
                     ("ais/autoResolveProblems.py", "Auto Resolve Problems (Afternoon)", 15)], # 13:15 VT
                14: [("engine/citizenhousingmobility.py", "Citizen housing mobility", 0), # 14:00 VT
                     ("ais/answertomessages.py --model local", "AI message responses", 5), # 14:05 VT
                     ("engine/createmarketgalley.py --goods", "Create Market Galley (Goods)", 10)], # 14:10 VT
                15: [("engine/dailyloanpayments.py", "Daily loan payments", 0), # 15:00 VT
                     ("engine/cleanTables.py", "Clean Old Table Records (Afternoon)", 5)], # 15:05 VT
                16: [("engine/citizenworkmobility.py", "Citizen work mobility", 0), # 16:00 VT
                     ("ais/answertomessages.py --model local", "AI message responses", 5)], # 16:05 VT
                17: [("engine/dailywages.py", "Daily wage payments", 0)], # 17:00 VT
                18: [("engine/dailyrentpayments.py", "Daily rent payments", 0)], # 18:00 VT
                19: [("engine/calculateIncomeAndTurnover.py", "Citizen Income and Turnover Calculation", 0), # 19:00 VT
                     ("engine/processStratagems.py", "Process Active Stratagems (Evening)", 5)], # 19:05 VT
                20: [ # ("ais/bidonlands.py", "AI land bidding", 0), # 20:00 VT
                     ("ais/delegateBusinesses.py", "AI Business Delegation", 5), # 20:05 VT
                     ("engine/createmarketgalley.py --construction", "Create Market Galley (Construction)", 10), # 20:10 VT
                     ("engine/review_grievances.py", "Review Grievances for Signoria", 15)], # 20:15 VT
                21: [("ais/buildbuildings.py --model local", "AI building construction", 0), # 21:00 VT
                     ("ais/automated_adjustleases.py --strategy standard", "Automated AI Lease Price Adjustment (Standard)", 30), # 21:30 VT
                     ("ais/thinkingLoop.py", "AI Thinking Loop & Process Queue", 45)], # 21:45 VT
                22: [("ais/automated_adjustrents.py --strategy standard", "Automated AI Rent Adjustment (Standard)", 5)], # 22:05 VT
                23: [("ais/automated_adjustpublicstoragecontracts.py", "Automated Public Storage Offers", 0)], # 23:00 VT
                0: [("ais/automated_adjustwages.py --strategy standard", "Automated AI Wage Adjustment (Standard)", 0), # 00:00 VT (Midnight)
                    ("ais/automated_adjuststoragequeriescontracts.py", "Automated Storage Queries", 5), # 00:05 VT
                    ("ais/qualifyRelationships.py --newOnly", "AI Relationship Qualification (New Only - Nightly)", 15)], # 00:15 VT
                1: [("ais/processnotifications.py", "AI notification processing", 0), # 1:00 VT  (processnotifications.py does not take --model)
                    ("engine/paystoragecontracts.py", "Process Storage Contract Payments", 5)], # 1:05 VT
                2: [("ais/answertomessages.py --model local", "AI message responses", 0), # 2:00 VT
                    ("engine/createmarketgalley.py", "Create Market Galley (Normal)", 5), # 2:05 VT
                    ("relevancies/calculateRelevancies.py", "Calculate Citizen Relevancies", 10)], # 2:10 VT
                3: [("engine/cleanTables.py", "Clean Old Table Records", 0), # 3:00 VT
                    ("engine/processStratagems.py", "Process Active Stratagems (Morning)", 5), # 3:05 VT
                    ("engine/theSynthesis.py", "The Synthesis - Substrate Consciousness Integration", 33), # 3:33 VT
                    ("reports/createReports.py", "Create Renaissance Reports", 50)], # 3:50 VT
                4: [("ais/answertomessages.py --model local", "AI message responses", 0), # 4:00 VT
                    ("engine/translateCodeToExperience.py", "Translate code changes to citizen experiences", 3), # 4:03 VT
                    ("ais/automated_managepublicsalesandprices.py --strategy standard", "Automated AI Public Sales & Pricing (Standard)", 5), # 4:05 VT
                    ("engine/processPassiveBuildings.py", "Process Passive Buildings (Wells/Cisterns)", 10)], # 4:10 VT
            }
            
            # Add processEncounters.py to run every hour at minute 45
            for hour in range(24):
                task_name = f"Process Citizen Encounters ({hour:02d}:45 VT)"
                encounter_task = ("relationships/processEncounters.py", task_name, 45) # Changed minute from 0 to 45
                if hour in tasks:
                    # Check if the task is already scheduled for this hour and minute to avoid duplicates
                    if not any(t[0] == "relationships/processEncounters.py" and t[2] == 45 for t in tasks[hour]):
                        tasks[hour].append(encounter_task)
                else:
                    tasks[hour] = [encounter_task]
            
            # Add emergency_food_distribution.py to run every hour at minute 15
            for hour in range(24):
                task_name = f"Emergency Food Distribution ({hour:02d}:15 VT)"
                food_task = ("engine/emergency_food_distribution_charity_contracts.py", task_name, 15)
                if hour in tasks:
                    # Check if the task is already scheduled for this hour and minute to avoid duplicates
                    if not any(t[0] == "engine/emergency_food_distribution_charity_contracts.py" and t[2] == 15 for t in tasks[hour]):
                        tasks[hour].append(food_task)
                else:
                    tasks[hour] = [food_task]
            
            # Add welfare_monitor.py to run every hour at minute 30
            for hour in range(24):
                task_name = f"Welfare Monitoring ({hour:02d}:30 VT)"
                monitor_task = ("engine/welfare_monitor.py", task_name, 30)
                if hour in tasks:
                    # Check if the task is already scheduled for this hour and minute to avoid duplicates
                    if not any(t[0] == "engine/welfare_monitor.py" and t[2] == 30 for t in tasks[hour]):
                        tasks[hour].append(monitor_task)
                else:
                    tasks[hour] = [monitor_task]
            
            
            # Check if there are tasks for the current Venice hour
            if current_hour_venice in tasks:
                tasks_for_this_hour_and_minute = tasks[current_hour_venice]
                if not isinstance(tasks_for_this_hour_and_minute, list):
                    log_message_invalid_task_format = f"Task entry for Venice hour {current_hour_venice} is not a list: {tasks_for_this_hour_and_minute}. Skipping."
                    print(log_message_invalid_task_format)
                else:
                    for task_entry in tasks_for_this_hour_and_minute:
                        if isinstance(task_entry, tuple) and len(task_entry) == 3:
                            script_path, task_name, target_minute = task_entry
                            if current_minute_venice == target_minute:
                                # Check if script_path includes arguments (e.g., "--strategy standard")
                                script_parts = script_path.split(" ", 1)
                                actual_script_path = script_parts[0]
                                script_args = script_parts[1].split() if len(script_parts) > 1 else []

                                print(f"Scheduler: Running task (Venice Time {current_hour_venice}:{target_minute:02d}): {task_name} from {actual_script_path} with args {script_args}")
                            
                                try:
                                    script_full_path = os.path.join(backend_dir_path, actual_script_path)
                                    
                                    command_to_run = ["python3", script_full_path] + script_args
                                    # Propagate forced_hour for hourly tasks if applicable
                                    if forced_hour is not None and actual_script_path in SCRIPTS_RESPECTING_FORCED_HOUR: # Use module-level constant
                                        command_to_run.extend(["--hour", str(forced_hour)])
                                    
                                    output_lines_hourly = []
                                    process = subprocess.Popen(
                                        command_to_run,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, # Redirect stderr to stdout
                                        text=True,
                                        bufsize=1, 
                                        universal_newlines=True,
                                        cwd=backend_dir_path  # Set working directory to backend
                                    )
                                    if process.stdout:
                                        for line in iter(process.stdout.readline, ''):
                                            stripped_line_hourly = line.strip()
                                            print(f"[{task_name}] {stripped_line_hourly}")
                                            output_lines_hourly.append(stripped_line_hourly)
                                        process.stdout.close()
                                    
                                    return_code = process.wait()
                                    log_output_hourly_telegram = "\n".join(output_lines_hourly[-20:])

                                    if return_code == 0:
                                        print(f"Successfully ran {task_name}")
                                    else:
                                        error_message_hourly = f"Error running task {task_name}. Return code: {return_code}"
                                        print(error_message_hourly)
                                        if "KeyboardInterrupt" not in log_output_hourly_telegram:
                                            telegram_message_hourly = (f"[X] Task Failed: {task_name}\n" # Replaced ❌
                                                                       f"Script: `{script_full_path}`\n"
                                                                       f"Return Code: {return_code}\n\n"
                                                                       f"```\n--- Last 20 lines of log ---\n{log_output_hourly_telegram}\n```")
                                            send_telegram_notification(telegram_message_hourly)
                                            # Create problem record for Arsenale to detect
                                            create_scheduler_problem(task_name, script_full_path, 
                                                                   f"Task failed with return code: {return_code}", 
                                                                   log_output_hourly_telegram)
                                        else:
                                            print(f"Scheduler (Hourly): KeyboardInterrupt detected for {task_name}. Skipping Telegram notification.")
                                except FileNotFoundError:
                                    error_message_hourly = f"Exception running task {task_name}: Script not found at {script_full_path}"
                                    print(error_message_hourly)
                                    send_telegram_notification(f"[X] Task Failed: {task_name}\nScript: `{script_full_path}`\nError: Script not found") # Replaced ❌
                                    # Create problem record for missing script
                                    create_scheduler_problem(task_name, script_full_path, 
                                                           "Script file not found", 
                                                           "The specified script does not exist at the expected path.")
                                except Exception as e:
                                    error_message_hourly = f"Exception running task {task_name}: {str(e)}"
                                    print(error_message_hourly)
                                    log_output_hourly_exception = "\n".join(output_lines_hourly[-20:]) if output_lines_hourly else "No specific script output captured before exception."
                                    if "KeyboardInterrupt" not in str(e) and "KeyboardInterrupt" not in log_output_hourly_exception:
                                        telegram_message_hourly_exception = (f"[X] Task Failed: {task_name}\n" # Replaced ❌
                                                                             f"Script: `{script_full_path}`\n"
                                                                             f"Exception: {str(e)}\n\n"
                                                                             f"```\n--- Last 20 lines of log (if any) ---\n{log_output_hourly_exception}\n```")
                                        send_telegram_notification(telegram_message_hourly_exception)
                                        # Create problem record for exception
                                        create_scheduler_problem(task_name, script_full_path, 
                                                               f"Exception: {str(e)}", 
                                                               log_output_hourly_exception)
                                    else:
                                        print(f"Scheduler (Hourly): KeyboardInterrupt detected during exception for {task_name}. Skipping Telegram notification.")
                        else:
                            log_message_invalid_tuple = f"Task entry item for Venice hour {current_hour_venice} is not a (script_path, task_name, target_minute) tuple: {task_entry}. Skipping."
                            print(log_message_invalid_tuple)
            
            # Special case for income distribution at 4 PM UTC (This was an old task, can be removed or re-evaluated)
            # This task is also at the top of the hour (current_minute_venice == 0)
            # if current_hour == 16: # This was the old income distribution
            #     print("Scheduler: Running income distribution")
            #     try:
            #         # Ensure the backend directory is in sys.path for the import
            #         backend_dir_path_for_import = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            #         if backend_dir_path_for_import not in sys.path:
            #             sys.path.append(backend_dir_path_for_import)
                    
            #         from distributeIncome import distribute_income # Assuming distributeIncome.py is in backend/
            #         distribute_income()
            #         print("Scheduler: Successfully ran income distribution")
            #     except ImportError:
            #         print(f"Exception running income distribution: Could not import distribute_income. Ensure distributeIncome.py is in the backend directory and backend directory is in PYTHONPATH.")
            #     except Exception as e:
            #         print(f"Exception running income distribution: {str(e)}")
        
        # Sleep for 60 seconds before checking again
        # The loop runs once per minute. Conditions for 5-min and hourly tasks are checked each time.
        time.sleep(60)

def start_scheduler(forced_hour: Optional[int] = None): # Added forced_hour parameter
    """Start the scheduler."""
    # Threads are non-daemonic by default.
    # A non-daemon thread will keep the main program alive until it completes.
    # Since run_scheduled_tasks is an infinite loop, this thread won't complete on its own.
    scheduler_thread = threading.Thread(target=run_scheduled_tasks, args=(forced_hour,))
    scheduler_thread.daemon = True  # Set thread as daemon
    scheduler_thread.start()
    print("Scheduler started in the foreground. Press Ctrl+C to stop.")
    try:
        # Keep the main thread alive, waiting for the scheduler thread.
        # This allows Ctrl+C to be caught by the main thread.
        scheduler_thread.join()
    except KeyboardInterrupt:
        print("\nScheduler stopping due to Ctrl+C...")
        # The program will exit, and non-daemon threads (like worker threads for tasks)
        # will also be terminated as part of the process shutdown.
    except Exception as e:
        print(f"\nScheduler encountered an error: {e}")
    finally:
        print("Scheduler has shut down.")

# Module-level variable to hold the scheduler thread instance when run by API
_api_scheduler_thread: Optional[threading.Thread] = None

def start_scheduler_background(forced_hour: Optional[int] = None):
    """Starts the scheduler tasks in a background daemon thread. For use by FastAPI."""
    global _api_scheduler_thread
    if _api_scheduler_thread and _api_scheduler_thread.is_alive():
        print("Scheduler background thread is already running.")
        return

    print("Attempting to start scheduler in background thread...")
    _api_scheduler_thread = threading.Thread(target=run_scheduled_tasks, args=(forced_hour,))
    _api_scheduler_thread.daemon = True  # Ensure it exits when main app exits
    _api_scheduler_thread.start()
    print("Scheduler background thread has been started.")

# --- Problem Creation Function ---
def create_scheduler_problem(task_name: str, script_path: str, error_message: str, log_output: str = "") -> bool:
    """Creates a problem record in Airtable when a scheduled task fails."""
    try:
        api_key = os.getenv('AIRTABLE_API_KEY')
        base_id = os.getenv('AIRTABLE_BASE_ID')
        
        if not api_key or not base_id:
            print(f"{Fore.YELLOW}⚠ Airtable credentials not configured. Cannot create problem record.{Style.RESET_ALL}")
            return False
        
        problems_table = Table(api_key, base_id, 'PROBLEMS')
        
        # Generate unique problem ID
        problem_id = f"scheduler_failure_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_name.replace(' ', '_').lower()}"
        
        # Truncate log output if too long
        if len(log_output) > 1000:
            log_output = log_output[-1000:] + "\n[...truncated...]"
        
        problem_data = {
            'ProblemId': problem_id,
            'Type': 'scheduler_task_failure',
            'Title': f"Scheduler Task Failed: {task_name}",
            'Description': f"The scheduled task '{task_name}' failed to execute properly.\n\nScript: {script_path}\n\nError: {error_message}\n\nLast log output:\n{log_output}",
            'Status': 'active',
            'Severity': 'High',  # Scheduler failures are typically high priority
            'AssetType': 'system',
            'Asset': 'scheduler',
            'Citizen': 'ConsiglioDeiDieci',  # System problems assigned to admin
            'CreatedAt': datetime.now().isoformat(),
            'Solutions': json.dumps([
                "Check if the script exists at the specified path",
                "Review the error message and fix any code issues",
                "Check for missing dependencies or environment variables",
                "Verify that required Airtable tables and API connections are working",
                "Review recent code changes that might have broken the script"
            ])
        }
        
        # Check if similar problem already exists (same task failure in last hour)
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        formula = f"AND({{Type}} = 'scheduler_task_failure', {{Title}} = '{problem_data['Title']}', {{CreatedAt}} >= '{one_hour_ago}')"
        existing_problems = problems_table.all(formula=formula, max_records=1)
        
        if not existing_problems:
            problems_table.create(problem_data)
            print(f"{Fore.GREEN}[OK] Created problem record for failed task: {task_name}{Style.RESET_ALL}")
            return True
        else:
            print(f"{Fore.YELLOW}⚠ Similar problem already exists for {task_name}, skipping creation{Style.RESET_ALL}")
            return False
            
    except Exception as e:
        print(f"{Fore.RED}[X] Failed to create problem record: {e}{Style.RESET_ALL}")
        return False

# --- Telegram Notification Function ---
def send_telegram_notification(message: str):
    """Sends a message to a Telegram chat via a bot."""
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = "1864364329" # Hardcoded Chat ID

    if not bot_token or not chat_id:
        print(f"{Fore.YELLOW}⚠ Telegram bot token or chat ID not configured. Cannot send notification.{Style.RESET_ALL}")
        return

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    # Truncate message if too long for Telegram (4096 chars limit)
    # Keep some buffer for Markdown and other overhead.
    MAX_TELEGRAM_MESSAGE_LENGTH = 4000 
    if len(message) > MAX_TELEGRAM_MESSAGE_LENGTH:
        message = message[:MAX_TELEGRAM_MESSAGE_LENGTH - 200] + "\n\n[...Message truncated...]" 
        # Ensure ``` is closed if truncated within a code block
        if message.count("```") % 2 != 0:
            message += "\n```"


    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"  # Optional: for formatting
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()  # Raise an exception for HTTP errors
        print(f"{Fore.GREEN}[OK] Telegram notification sent successfully.{Style.RESET_ALL}") # Replaced ✓
    except requests.exceptions.RequestException as e:
        print(f"{Fore.RED}[X] Failed to send Telegram notification: {e}{Style.RESET_ALL}") # Replaced ✗
    except Exception as e_gen:
        print(f"{Fore.RED}[X] An unexpected error occurred while sending Telegram notification: {e_gen}{Style.RESET_ALL}") # Replaced ✗

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the La Serenissima task scheduler.")
    parser.add_argument(
        "--hour",
        type=int,
        choices=range(24), # 0-23
        metavar="[0-23]",
        help="Force the scheduler to operate as if it's this hour in Venice time (0-23). Minutes and seconds will tick normally."
    )
    args = parser.parse_args()

    # Start the scheduler, passing the forced hour if provided
    start_scheduler(forced_hour=args.hour)
