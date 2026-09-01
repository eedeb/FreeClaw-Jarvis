"""
Mark 5 Free Version - Voice Assistant Only
This version includes only basic speaking/listening capabilities.
All advanced features (vision, automation, memory, etc.) are removed.
"""

import os
import sys
import eel
import threading
import asyncio
import time
from groq import Groq
from os import environ
import json

# Only the essential voice modules
from modules.vocalize.coqui import speak
from modules.vocalize.speechjs import SpeechToTextListener
from resource_path import resource_path, get_user_data_dir

# Speech-to-text listener
listener = SpeechToTextListener()

# Initialize eel with the UI folder
if getattr(sys, 'frozen', False):
    ui_path = resource_path('ui')
    eel.init(ui_path)
else:
    eel.init('ui')

# Paths
base_dir = get_user_data_dir()
icon_path = resource_path(os.path.join('Assets', 'logo.png'))

# Event loop shared with the speech coroutines
main_event_loop = None


def load_api_key():
    """Load Groq API key from config file"""
    config_file = os.path.join(get_user_data_dir(), 'cache', 'config.json')
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

                groq_keys = config.get('groq_api_key_api_keys', [])
                if isinstance(groq_keys, list) and len(groq_keys) > 0:
                    preferred_key_id = config.get('groq_api_key_preferred_key_id')
                    if preferred_key_id:
                        for k in groq_keys:
                            if k.get('id') == preferred_key_id and k.get('status') == 'active':
                                return k.get('key')

                    for k in groq_keys:
                        if k.get('status') == 'active':
                            return k.get('key')

                return config.get('groq_api_key')
        except:
            pass
    return None


api_key = load_api_key()
if api_key:
    client = Groq(api_key=api_key)
else:
    client = None
    print("Warning: No API key found. Please configure your Groq API key.")

# Rolling conversation history
conversation_history = []

def AssistantFunction(prompt: str, model: str = "openai/gpt-oss-120b") -> str:
    """
    Simple assistant function - just conversation, no function calling
    """
    if not client:
        return "API key not configured. Please set up your Groq API key in settings."

    try:
        # Add the user message to history
        conversation_history.append({
            "role": "user",
            "content": prompt
        })

        # Keep only the last 10 turns
        if len(conversation_history) > 10:
            conversation_history[:] = conversation_history[-10:]

        # System prompt
        system_message = {
            "role": "system",
            "content": """You are Mark 5 Free, a helpful voice assistant. You can:
- Answer questions
- Have conversations
- Provide information
- Give advice

Keep responses concise and conversational. You are the FREE version with basic capabilities only."""
        }

        # Build the full message list
        messages = [system_message] + conversation_history

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        assistant_message = response.choices[0].message.content

        # Add the assistant reply to history
        conversation_history.append({
            "role": "assistant",
            "content": assistant_message
        })

        return assistant_message

    except Exception as e:
        print(f"Error in AssistantFunction: {e}")
        return f"I encountered an error: {str(e)}"


async def run_speech_task(text):
    """Run speech synthesis task"""
    try:
        eel.startSpeakingAnimation()
        await speak(text)
        eel.stopSpeakingAnimation()
    except Exception as e:
        try:
            eel.stopSpeakingAnimation()
        except:
            pass
        import logging
        logging.error(f"Speech task error: {e}")

def speak_text(text):
    """Helper function to speak text"""
    try:
        import pygame
        pygame.mixer.stop()
    except Exception:
        pass
    future = asyncio.run_coroutine_threadsafe(run_speech_task(text), main_event_loop)
    future.result()


@eel.expose
def process_user_input(user_input):
    """Process user input and generate response"""
    try:
        print(f"User: {user_input}")

        # Get the assistant's reply
        response = AssistantFunction(user_input)
        print(f"Assistant: {response}")

        # Speak it out loud
        speak_text(response)

        return response
    except Exception as e:
        error_msg = f"Error processing input: {str(e)}"
        print(error_msg)
        return error_msg

@eel.expose
def start_listening():
    """Start listening for voice input"""
    try:
        listener.start()
        return True
    except Exception as e:
        print(f"Error starting listener: {e}")
        return False

@eel.expose
def stop_listening():
    """Stop listening for voice input"""
    try:
        listener.stop()
        return True
    except Exception as e:
        print(f"Error stopping listener: {e}")
        return False

@eel.expose
def get_version_info():
    """Return version information"""
    return {
        "version": "Free 1.0",
        "name": "Mark 5 Free",
        "features": ["Voice Conversation", "Basic Q&A"]
    }


def main():
    """Main entry point for the free version"""
    global main_event_loop

    # Create a dedicated event loop for the speech coroutines
    main_event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_event_loop)

    # Launch the eel UI
    try:
        eel.start(
            'index.html',
            size=(1200, 800),
            port=8080,
            mode='chrome',
            cmdline_args=['--disable-http-cache'],
            block=True
        )
    except Exception as e:
        print(f"Error starting application: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
