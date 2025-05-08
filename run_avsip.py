# run_avsip.py

import argparse
import logging
import os
import sys
import time

# Ensure the src directory is in the Python path if running from root
# This allows importing from 'avsip' package (src.avsip)
# If 'src' is not directly in PYTHONPATH, this might be needed.
# However, if running as 'python -m avsip.run_module' from root, this is not needed.
# For a simple script in root, this helps:
current_dir = os.path.dirname(os.path.abspath(__file__))
# Assuming 'src' is at the same level as this script or one level up if script is in 'examples'
# If script is in root, and 'src' is a subdir:
sys.path.insert(0, os.path.join(current_dir, 'src'))
# If script is in 'examples' and 'src' is sibling of 'examples':
# sys.path.insert(0, os.path.join(os.path.dirname(current_dir), 'src'))


# Now import AVSIP from the avsip package
try:
    from avsip.core import AVSIP
except ImportError as e:
    print(f"Error: Could not import AVSIP. Ensure 'src' directory is in PYTHONPATH or script is run correctly: {e}")
    sys.exit(1)

# Initialize a logger for this script, distinct from AVSIP's internal logger if needed,
# or rely on AVSIP's basicConfig if it's called first.
# For simplicity, AVSIP's _configure_logging will set up global basicConfig.
script_logger = logging.getLogger("run_avsip") # Using a named logger

def main():
    """
    Main function to parse arguments, initialize, and run the AVSIP application.
    """
    parser = argparse.ArgumentParser(description="AVSIP - Akita Vehicle Sensor Integration Plugin")
    parser.add_argument(
        "--config",
        default="avsip_config.json",
        help="Path to the AVSIP configuration JSON file (default: avsip_config.json in current dir)"
    )
    args = parser.parse_args()

    # Basic logging setup until AVSIP's config is loaded and its logger takes over.
    # This ensures that errors finding the config file are logged.
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    script_logger.info(f"Starting AVSIP application with config file: {args.config}")

    if not os.path.exists(args.config):
        script_logger.error(f"Configuration file '{args.config}' not found. Exiting.")
        # Create a default config file if one doesn't exist to guide the user.
        try:
            from avsip.config_manager import DEFAULT_CONFIG # Import default config
            import json
            if not os.path.exists("avsip_config.example.json"): # Only create if example also missing
                with open("avsip_config.example.json", "w") as f:
                    json.dump(DEFAULT_CONFIG, f, indent=4)
                script_logger.info("A default 'avsip_config.example.json' has been created. "
                                   "Please copy it to 'avsip_config.json' and customize it.")
        except Exception as e_cfg:
            script_logger.error(f"Could not create default config example: {e_cfg}")
        sys.exit(1)

    avsip_app = None
    try:
        # AVSIP's __init__ will load the config and set up more detailed logging.
        avsip_app = AVSIP(config_file_path=args.config)
        avsip_app.start()

        # Keep the main thread alive while AVSIP runs in its own threads.
        # Listen for KeyboardInterrupt (Ctrl+C) to gracefully stop.
        while True:
            # Check if AVSIP's main data thread is alive. If not, something went wrong.
            if avsip_app._data_thread and not avsip_app._data_thread.is_alive():
                script_logger.error("AVSIP data loop thread is no longer alive. Exiting.")
                break
            time.sleep(1) # Keep main thread responsive

    except KeyboardInterrupt:
        script_logger.info("KeyboardInterrupt received. Initiating AVSIP shutdown...")
    except FileNotFoundError: # Already handled above, but as a safeguard
        script_logger.error(f"Configuration file '{args.config}' not found during AVSIP instantiation. Exiting.")
    except ImportError: # Already handled, but as a safeguard
        script_logger.error("Failed to import AVSIP components. Ensure project structure and PYTHONPATH are correct.")
    except Exception as e:
        script_logger.critical(f"An unhandled critical exception occurred in run_avsip: {e}", exc_info=True)
    finally:
        if avsip_app:
            script_logger.info("Ensuring AVSIP is stopped...")
            avsip_app.stop()
        script_logger.info("AVSIP application has shut down.")

if __name__ == "__main__":
    main()
