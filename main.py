import asyncio

# Import the main customer service agent
from customer_service_agent.agent import customer_service_agent
from dotenv import load_dotenv
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService, SessionNotFoundError
from utils import add_user_query_to_history, call_agent_async

load_dotenv()

# ===== PART 1: Initialize In-Memory Session Service =====
# Using in-memory storage for this example (non-persistent)
session_service = InMemorySessionService()


# ===== PART 2: Define Initial State Template =====
# This initial_state_template will be used as a template for new users.
# The 'user_name' will be dynamically set per user.
initial_state_template = {
    "user_name": "",  # To be filled dynamically
    "purchased_courses": [],
    "interaction_history": [],
}


async def main_async():
    # Get user name first
    current_user_name_input = input("Please enter your name: ")
    if not current_user_name_input.strip():
        current_user_name = "Guest"  # Default if no name is entered or just whitespace
        print("No valid name entered, proceeding as 'Guest'.")
    else:
        current_user_name = current_user_name_input.strip()

    # Setup constants
    APP_NAME = "Customer Support"
    USER_ID = current_user_name  # Use the entered name as USER_ID
    # Deterministic session ID per user for potential session resumption
    SESSION_ID = f"{USER_ID}_main_session"

    # ===== PART 3: Session Creation/Loading =====
    current_session = None
    try:
        # Attempt to load an existing session
        current_session = session_service.get_session(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        # Use user_name from session state if available, otherwise fall back to USER_ID
        loaded_user_name = current_session.state.get('user_name', USER_ID)
        print(f"Welcome back, {loaded_user_name}! Loaded existing session: {current_session.id}")
    except SessionNotFoundError:
        print(f"Welcome, {USER_ID}! Creating new session...")
        # Prepare user-specific initial state
        user_initial_state = initial_state_template.copy()
        user_initial_state["user_name"] = USER_ID  # Set the actual user name

        # Create a new session if one doesn't exist
        current_session = session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,  # Use the deterministic session ID
            state=user_initial_state,
        )
        print(f"New session created: {current_session.id}")
    except Exception as e:
        print(f"An unexpected error occurred during session handling: {e}")
        print("Proceeding with a temporary guest session due to error.")
        # Fallback to a temporary, uniquely identified guest session in case of other errors
        # Note: session_service._generate_id() might be an internal method.
        # For robustness, a more public way to ensure uniqueness or a simpler fallback might be needed.
        # For this example, we'll assume it works or use a simpler random suffix if not.
        try:
            error_id_suffix = session_service._generate_id()
        except AttributeError:
            import random
            import string
            error_id_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))

        USER_ID = f"Guest_Error_{error_id_suffix}"
        SESSION_ID = f"{USER_ID}_main_session" # This session is unlikely to be resumed
        user_initial_state = initial_state_template.copy()
        user_initial_state["user_name"] = USER_ID
        current_session = session_service.create_session(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            state=user_initial_state,
        )
        print(f"Error fallback session created: {current_session.id}")

    if current_session is None:
        print("Critical error: Session could not be established. Exiting.")
        return

    # ===== PART 4: Agent Runner Setup =====
    # Create a runner with the main customer service agent
    runner = Runner(
        agent=customer_service_agent,
        app_name=APP_NAME,
        session_service=session_service # Pass the session service instance
    )

    # ===== PART 5: Interactive Conversation Loop =====
    print("\nWelcome to Customer Service Chat!")
    print("Type 'exit' or 'quit' to end the conversation.\n")

    while True:
        # Use the user_name from the current session's state for the prompt
        prompt_user_name = current_session.state.get('user_name', USER_ID)
        user_input = input(f"{prompt_user_name}: ")

        # Check if user wants to exit
        if user_input.lower() in ["exit", "quit"]:
            print("Ending conversation. Goodbye!")
            break

        active_session_id = current_session.id

        # Update interaction history with the user's query
        add_user_query_to_history(
            session_service, APP_NAME, USER_ID, active_session_id, user_input
        )

        # Process the user query through the agent
        await call_agent_async(runner, USER_ID, active_session_id, user_input)

        # Refresh current_session object to get the latest state after agent interaction
        # This is important if the agent modifies the state (e.g. user_name, purchases)
        try:
            current_session = session_service.get_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=active_session_id
            )
        except SessionNotFoundError:
            print("Error: Session lost during interaction. Exiting.")
            break
        except Exception as e:
            print(f"Error refreshing session state: {e}. Exiting.")
            break

        if current_session is None: # Should ideally not happen if exceptions are caught
            print("Critical error: Session became None during loop. Exiting.")
            break

    # ===== PART 6: State Examination =====
    # Show final session state using the active session ID from the loop's last valid session
    if current_session: # Ensure current_session is not None before trying to access its id
        final_active_session_id = current_session.id
        try:
            final_session = session_service.get_session(
                app_name=APP_NAME, user_id=USER_ID, session_id=final_active_session_id
            )
            print("\nFinal Session State:")
            for key, value in final_session.state.items():
                print(f"{key}: {value}")
        except SessionNotFoundError:
            print(f"Could not retrieve final session state for {final_active_session_id}. It might have been deleted or an error occurred.")
        except Exception as e:
            print(f"Error retrieving final session state: {e}")
    else:
        print("No active session to examine at the end.")


def main():
    """Entry point for the application."""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
