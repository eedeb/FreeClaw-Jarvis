import eel
import random
import os
import base64
import requests
import threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor, as_completed

widget_counter = 0
def get_next_widget_id():
    global widget_counter
    widget_counter += 1
    return f'widget_{widget_counter}'

# Video summarization queue system
_summarization_queue = Queue()
_summarization_processing = False
_summarization_lock = threading.Lock()
_cancellation_flags = {}  # Track cancellation requests: {title: True/False}

def _summarization_worker():
    """Background worker that processes video summarization queue one at a time."""
    global _summarization_processing
    
    while True:
        try:
            # Get next item from queue (blocks until available)
            title = _summarization_queue.get()
            
            if title is None:  # Shutdown signal
                break
            
            print(f"[Summarization Queue] Processing: {title} (Queue size: {_summarization_queue.qsize()})")
            
            # Reset cancellation flag for this title
            with _summarization_lock:
                _cancellation_flags[title] = False
            
            try:
                # Update indicator to loading when summarization starts (if transcript is available)
                try:
                    eel.updateTranscriptIndicator(title, 'loading')()
                except Exception as e:
                    print(f"[Summarization Queue] Could not update indicator to loading: {e}")
                
                # Process the summarization (this will update indicator to complete when done)
                result = summarize_video_widget(title)
                
                # Check if cancelled
                with _summarization_lock:
                    was_cancelled = _cancellation_flags.get(title, False)
                    if title in _cancellation_flags:
                        del _cancellation_flags[title]
                
                if was_cancelled:
                    print(f"[Summarization Queue] Cancelled: {title}")
                    try:
                        eel.updateTranscriptIndicator(title, 'cancelled')()
                    except Exception as e:
                        print(f"[Summarization Queue] Could not update indicator to cancelled: {e}")
                else:
                    print(f"[Summarization Queue] Completed: {title} - Result: {str(result)[:100]}...")
            except InterruptedError as e:
                # Cancellation was requested
                print(f"[Summarization Queue] Summarization cancelled for {title}: {e}")
                try:
                    eel.updateTranscriptIndicator(title, 'cancelled')()
                except Exception as e2:
                    print(f"[Summarization Queue] Could not update indicator to cancelled: {e2}")
                # Clean up cancellation flag
                with _summarization_lock:
                    if title in _cancellation_flags:
                        del _cancellation_flags[title]
            except Exception as e:
                print(f"[Summarization Queue] Error processing {title}: {e}")
                import traceback
                traceback.print_exc()
                # Clean up cancellation flag on error
                with _summarization_lock:
                    if title in _cancellation_flags:
                        del _cancellation_flags[title]
            finally:
                # Mark task as done
                _summarization_queue.task_done()
                
        except Exception as e:
            print(f"[Summarization Queue] Worker error: {e}")
            import traceback
            traceback.print_exc()
    
    _summarization_processing = False
    print("[Summarization Queue] Worker stopped")

# Start the worker thread
_summarization_thread = threading.Thread(target=_summarization_worker, daemon=True)
_summarization_thread.start()
print("[Summarization Queue] Worker thread started")

def get_next_video_number():
    """Get next video number from JavaScript counter (source of truth)"""
    try:
        # Get number from JavaScript - it handles the incrementing
        js_number = eel.getNextVideoNumber()()
        if js_number is not None:
            return int(js_number)
    except Exception as e:
        # If JavaScript call fails, use a simple fallback
        print(f"Note: Could not get video number from JavaScript: {e}")
    
    # Fallback: use a simple incrementing counter (won't sync with JS, but works)
    # This should rarely be used since JavaScript is usually available
    if not hasattr(get_next_video_number, '_fallback_counter'):
        get_next_video_number._fallback_counter = 0
    get_next_video_number._fallback_counter += 1
    return get_next_video_number._fallback_counter

@eel.expose
def create_text_widget(text, title="INFORMATION", group_id=None):
    """Create a text widget with the given content"""
    widget_id = get_next_widget_id()
    # Random position within viewport
    x = random.randint(50, 800)
    y = random.randint(50, 400)
    eel.createWidget(widget_id, title, 'text', text, x, y, None, None, group_id)
    return widget_id

@eel.expose
def create_notes_widget(title="NOTES", initial_text="", group_id=None):
    """Create an editable notes widget with the given title and optional initial text"""
    widget_id = get_next_widget_id()
    # Random position within viewport
    x = random.randint(50, 800)
    y = random.randint(50, 400)
    eel.createWidget(widget_id, title, 'notes', initial_text, x, y, None, None, group_id)
    return widget_id

@eel.expose
def update_widget_content(widget_id, content):
    """Update the content of an existing widget"""
    try:
        eel.updateWidgetContent(widget_id, content)()
        return True
    except Exception as e:
        print(f"[UI] Error updating widget content: {e}")
        return False

@eel.expose
def create_api_key_exhaustion_widget(service_name="Gemini", exhausted_count=0, total_count=0):
    """Create a widget to notify user that API keys are exhausted"""
    widget_id = get_next_widget_id()
    x = random.randint(100, 800)
    y = random.randint(100, 600)
    
    # Create a warning message
    if exhausted_count > 0 and total_count > 0:
        message = f"âš ï¸ {service_name} API Keys Exhausted\n\n"
        message += f"All {exhausted_count} of {total_count} active {service_name} API key(s) have reached their quota limits.\n\n"
        message += "To continue using browser automation:\n"
        message += "â€¢ Add more API keys in Settings\n"
        message += "â€¢ Wait for quota limits to reset\n"
        message += "  (Daily limits: ~24 hours, Rate limits: minutes)\n\n"
        message += "Browser automation will resume automatically once a key becomes available."
    else:
        message = f"âš ï¸ {service_name} API Keys Exhausted\n\n"
        message += f"All {service_name} API keys have reached their quota limits.\n\n"
        message += "Please add more API keys in Settings or wait for quotas to reset."
    
    title = f"{service_name} API Keys Exhausted"
    eel.createWidget(widget_id, title, 'text', message, x, y, None, None, None)
    return widget_id

@eel.expose
def create_calculator_widget(group_id=None):
    """Create a calculator widget with Desmos scientific calculator"""
    widget_id = get_next_widget_id()
    # Random position within viewport
    x = random.randint(50, 800)
    y = random.randint(50, 400)
    # Use 'calculator' type and pass the Desmos URL as content
    # Set size to 1200x900 to properly fit the Desmos calculator iframe
    eel.createWidget(widget_id, "CALCULATOR", 'calculator', 'https://www.desmos.com/scientific', x, y, 1200, 900, group_id)
    return widget_id

@eel.expose
def create_video_widget(video_path, title=None, skip_auto_summarize=False):
    """Create a video widget with automatically numbered title (VIDEO 1, VIDEO 2, etc.)
    
    Args:
        video_path: URL or path to the video
        title: Optional title for the video widget
        skip_auto_summarize: If True, skip automatic summarization (used when restoring from workspace)
    """
    import time
    import threading
    
    widget_id = get_next_widget_id()
    x = random.randint(50, 800)
    y = random.randint(50, 400)
    
    # Get the next video number if title not provided
    if title is None:
        video_number = get_next_video_number()
        title = f"VIDEO {video_number}"
    
    eel.createWidget(widget_id, title, 'video', video_path, x, y)
    
    # Only automatically queue summarization if not skipping (i.e., not restoring from workspace)
    if not skip_auto_summarize:
        # Automatically queue the video for summarization (same as drag-and-drop)
        def queue_summarization():
            # Add a small delay to ensure widget is fully created
            time.sleep(1.0)
            try:
                print(f"[Auto-summarize] Queuing automatic summarization for '{title}'")
                # Queue the video for summarization
                summarize_video_widget_from_title(title)
            except Exception as e:
                print(f"[Auto-summarize] Error queueing video '{title}': {e}")
        
        # Start summarization in a background thread
        summarization_thread = threading.Thread(target=queue_summarization, daemon=True)
        summarization_thread.start()
    else:
        print(f"[Video Widget] Skipping auto-summarization for '{title}' (restoring from workspace)")
    
    return widget_id

@eel.expose
def update_bottom_left(text):
    """
    Updates the content of the bottom-left output area in the UI.

    Args:
        text (str): The text to display in the bottom-left output.
    """
    eel.spawn(eel.updateBottomLeftOutput(text))  # Use eel.spawn for thread safety

@eel.expose
def create_image_widget(image_path, title="IMAGE", custom_width=None, custom_height=None, group_id=None):
    widget_id = get_next_widget_id()
    x = random.randint(50, 800)
    y = random.randint(50, 400)

    if image_path.startswith("data:image/"):  # Check if it's a data URL (base64 encoded image)
        # Data URL - use it directly
        if custom_width and custom_height:
            eel.createWidget(widget_id, title, 'image', image_path, x, y, custom_width, custom_height, group_id)
        else:
            eel.createWidget(widget_id, title, 'image', image_path, x, y, None, None, group_id)
    elif os.path.exists(image_path):  # Check if path is local
        with open(image_path, "rb") as img_file:
            b64_encoded_image = base64.b64encode(img_file.read()).decode('utf-8')
            data_url = f"data:image/png;base64,{b64_encoded_image}"  # or the correct MIME type
            
            # Pass custom size if provided
            if custom_width and custom_height:
                eel.createWidget(widget_id, title, 'image', data_url, x, y, custom_width, custom_height, group_id)
            else:
                eel.createWidget(widget_id, title, 'image', data_url, x, y, None, None, group_id)
    elif image_path.startswith("http"):  # Check if it's a URL
        # Pass custom size if provided
        if custom_width and custom_height:
            eel.createWidget(widget_id, title, 'image', image_path, x, y, custom_width, custom_height, group_id)
        else:
            eel.createWidget(widget_id, title, 'image', image_path, x, y, None, None, group_id)
    else:
        print(f"Error: Invalid image path or URL: {image_path[:100]}...")  # Truncate long paths in error message
        # Handle the error (e.g., create a text widget with an error message)
        error_msg = f"Error: Invalid image path or URL (truncated for display)"
        eel.createWidget(widget_id, "Error", "text", error_msg, x, y, None, None, group_id)

    return widget_id

@eel.expose
def create_weather_widget(weather_data, title="WEATHER", group_id=None):
    widget_id = get_next_widget_id()
    # Center the weather widget on screen instead of random positioning
    x = 400  # Center horizontally
    y = 200  # Center vertically
    eel.createWidget(widget_id, title, 'weather', weather_data, x, y, None, None, group_id)
    return widget_id

@eel.expose
def create_time_widget(group_id=None, military_time=False):
    """Create a time widget that displays current time and updates automatically
    
    Args:
        group_id: Optional group ID for widget grouping
        military_time: If True, use 24-hour format. If False, use 12-hour AM/PM format (default)
    """
    widget_id = get_next_widget_id()
    # Center the time widget on screen
    x = 400  # Center horizontally
    y = 200  # Center vertically
    
    # Get current time data - only time, no date
    import datetime
    now = datetime.datetime.now()
    
    if military_time:
        # 24-hour format (military time)
        hour = now.strftime('%H')  # 00-23
        minute = now.strftime('%M')
        time_data = {
            'time': f"{hour}:{minute}",
            'format': 'military'
        }
    else:
        # 12-hour format with AM/PM (default)
        hour12 = now.strftime('%I')  # Keep leading zero (01-12)
        minute = now.strftime('%M')
        ampm = now.strftime('%p')
        time_data = {
            'time': f"{hour12}:{minute} {ampm}",
            'format': '12-hour'
        }
    
    # Pass as JSON string
    import json
    time_data_json = json.dumps(time_data)
    eel.createWidget(widget_id, "TIME", 'time', time_data_json, x, y, None, None, group_id)
    return widget_id

@eel.expose
def create_timer_widget(duration_seconds, group_id=None):
    """Create a countdown timer widget
    
    Args:
        duration_seconds: Duration of the timer in seconds
        group_id: Optional group ID for widget grouping
    """
    widget_id = get_next_widget_id()
    # Center the timer widget on screen
    x = 400  # Center horizontally
    y = 200  # Center vertically
    
    # Pass timer data as JSON string
    import json
    timer_data = {
        'duration_seconds': duration_seconds,
        'start_time': None  # Will be set in JavaScript when widget is created
    }
    timer_data_json = json.dumps(timer_data)
    eel.createWidget(widget_id, "TIMER", 'timer', timer_data_json, x, y, None, None, group_id)
    return widget_id

@eel.expose
def create_alarm_widget(label, group_id=None):
    """Create an alarm widget that shows when an alarm goes off
    
    Args:
        label: The alarm label/message to display
        group_id: Optional group ID for widget grouping
    """
    widget_id = get_next_widget_id()
    # Center the alarm widget on screen
    x = 400  # Center horizontally
    y = 200  # Center vertically
    
    # Pass alarm data as JSON string
    import json
    alarm_data = {
        'label': label,
        'triggered_at': None  # Will be set in JavaScript when widget is created
    }
    alarm_data_json = json.dumps(alarm_data)
    eel.createWidget(widget_id, "ALARM", 'alarm', alarm_data_json, x, y, None, None, group_id)
    return widget_id

@eel.expose
def create_reminder_widget(label, group_id=None):
    """Create a reminder widget that shows when a reminder triggers
    
    Args:
        label: The reminder message to display
        group_id: Optional group ID for widget grouping
    """
    widget_id = get_next_widget_id()
    # Center the reminder widget on screen
    x = 400  # Center horizontally
    y = 200  # Center vertically
    
    # Pass reminder data as JSON string
    import json
    reminder_data = {
        'label': label,
        'triggered_at': None  # Will be set in JavaScript when widget is created
    }
    reminder_data_json = json.dumps(reminder_data)
    eel.createWidget(widget_id, "REMINDER", 'reminder', reminder_data_json, x, y, None, None, group_id)
    return widget_id
    print(f"Creating time widget: {widget_id}, data: {time_data_json}")
    try:
        # Call eel.createWidget - same pattern as create_weather_widget
        # This should trigger the JavaScript createWidget function
        result = eel.createWidget(widget_id, "TIME", 'time', time_data_json, x, y, None, None, group_id)
        print(f"eel.createWidget returned: {result}")
        print(f"eel.createWidget called successfully for time widget")
    except Exception as e:
        import traceback
        print(f"Error calling eel.createWidget for time widget: {e}")
        traceback.print_exc()
    return widget_id

@eel.expose
def get_all_widgets():
    """Get information about all widgets currently on the UI"""
    import time
    
    try:
        print(f"[get_all_widgets] Called from Python")
        
        # Try multiple times with small delays to handle timing issues
        max_attempts = 3
        widgets = None
        
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    # Small delay between retries
                    time.sleep(0.2)
                    print(f"[get_all_widgets] Retry attempt {attempt + 1}/{max_attempts}")
                
                widgets = eel.getAllWidgets()()
                
                if widgets is not None:
                    print(f"[get_all_widgets] Got {len(widgets) if widgets else 0} widgets from JavaScript")
                    if widgets:
                        for widget in widgets:
                            print(f"[get_all_widgets] Widget: {widget.get('title', 'NO TITLE')} ({widget.get('type', 'unknown')})")
                        break
                    else:
                        # Got None, try again
                        if attempt < max_attempts - 1:
                            continue
                        else:
                            print(f"[get_all_widgets] No widgets returned after {max_attempts} attempts")
                            return []
                else:
                    # Got None, try again
                    if attempt < max_attempts - 1:
                        continue
                    else:
                        print(f"[get_all_widgets] No widgets returned after {max_attempts} attempts")
                        return []
            except Exception as e:
                print(f"[get_all_widgets] Attempt {attempt + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    continue
                else:
                    raise
        
        return widgets if widgets is not None else []
    except Exception as e:
        print(f"[get_all_widgets] Error getting all widgets: {e}")
        import traceback
        traceback.print_exc()
        return []

@eel.expose
def check_transcript_availability(video_id):
    """Check if a YouTube video has transcript available."""
    try:
        from Functions.YTSummarize import get_transcript
        import re
        
        # Extract video ID if URL is provided
        if "youtube.com" in video_id or "youtu.be" in video_id:
            video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', video_id)
            if video_id_match:
                video_id = video_id_match.group(1)
        
        # Construct URL
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Try to get transcript (this will return None if not available)
        transcript = get_transcript(video_url)
        
        # Check if transcript is available (not None and not an error message)
        if transcript and isinstance(transcript, str):
            # Check if it's an error message
            error_indicators = [
                "rate limit", "transcripts are disabled", "cannot provide",
                "no transcript found", "connection error", "could not retrieve",
                "failed to fetch", "blocked", "not available", "api key"
            ]
            transcript_lower = transcript.lower()
            is_error = any(indicator in transcript_lower for indicator in error_indicators)
            
            if not is_error and len(transcript) >= 200:
                return {"available": True, "status": "available"}
        
        return {"available": False, "status": "unavailable"}
    except Exception as e:
        print(f"[check_transcript_availability] Error: {e}")
        return {"available": False, "status": "unknown"}

def get_youtube_video_metadata(video_id):
    """Get YouTube video metadata (title, description, channel) using YouTube API or web scraping"""
    try:
        # Try YouTube Data API first if available
        import os
        api_key = os.getenv("YOUTUBE_API_KEY")
        if api_key:
            try:
                url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={api_key}"
                response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("items"):
                        snippet = data["items"][0]["snippet"]
                        return {
                            "title": snippet.get("title"),
                            "description": snippet.get("description", "")[:500]  # Limit description length
                        }
            except Exception as e:
                print(f"[get_youtube_video_metadata] YouTube API error: {e}")
        
        # Fallback: Try web scraping
        try:
            from Functions.YTSummarize import get_video_info_from_web
            video_info = get_video_info_from_web(video_id)
            if video_info:
                return {
                    "title": video_info.get("title"),
                    "description": video_info.get("description", "")[:500] if video_info.get("description") else None
                }
        except Exception as e:
            print(f"[get_youtube_video_metadata] Web scraping error: {e}")
        
        return None
    except Exception as e:
        print(f"[get_youtube_video_metadata] Error getting metadata: {e}")
        return None

def _is_cancelled(title):
    """Check if summarization for this title has been cancelled"""
    with _summarization_lock:
        return _cancellation_flags.get(title, False)

def _get_api_key_from_config(config_file, service_name):
    """Get API key from config, supporting both multi-key and legacy formats."""
    import json

    if not os.path.exists(config_file):
        return None

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception:
        return None

    # Multi-key format: <service>_api_keys + <service>_preferred_key_id
    api_keys_key = f"{service_name}_api_keys"
    preferred_key_key = f"{service_name}_preferred_key_id"
    key_entries = config.get(api_keys_key, [])

    if isinstance(key_entries, list) and key_entries:
        preferred_id = config.get(preferred_key_key)

        if preferred_id:
            for entry in key_entries:
                if (
                    isinstance(entry, dict)
                    and entry.get("id") == preferred_id
                    and entry.get("status") == "active"
                    and entry.get("key")
                ):
                    return entry.get("key")

        for entry in key_entries:
            if isinstance(entry, dict) and entry.get("status") == "active" and entry.get("key"):
                return entry.get("key")

    # Legacy single-key format
    key_value = config.get(service_name)
    if isinstance(key_value, str) and key_value.strip():
        return key_value.strip()

    return None

def summarize_video_widget(title):
    """Summarize a video widget - tries transcript first, falls back to metadata, uses Groq for summarization"""
    print(f"[summarize_video_widget] ====== STARTING SUMMARIZATION FOR '{title}' ======")
    
    # Check for cancellation at the start
    if _is_cancelled(title):
        print(f"[summarize_video_widget] Cancellation detected at start for '{title}'")
        raise InterruptedError("Summarization cancelled by user")
    
    try:
        print(f"[summarize_video_widget] Step 1: Getting widget info for title: '{title}'")
        
        # Get widget info
        widget_info = get_widget_by_title(title)
        print(f"[summarize_video_widget] Step 1 result: widget_info = {widget_info}")
        
        if not widget_info:
            print(f"[summarize_video_widget] Step 1 FAILED: Widget not found")
            # Check if the title parameter might be a YouTube URL or video ID
            import re
            video_id = None
            video_url = None
            
            # Check if it's a YouTube URL
            youtube_url_pattern = r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([0-9A-Za-z_-]{11})'
            url_match = re.search(youtube_url_pattern, title)
            if url_match:
                video_id = url_match.group(1)
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                print(f"[summarize_video_widget] Detected YouTube URL in title parameter, extracted video ID: {video_id}")
            # Check if it's just a video ID (11 characters, alphanumeric)
            elif re.match(r'^[0-9A-Za-z_-]{11}$', title.strip()):
                video_id = title.strip()
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                print(f"[summarize_video_widget] Detected video ID in title parameter: {video_id}")
            
            if video_id:
                # Use the video ID/URL directly to summarize
                print(f"[summarize_video_widget] Proceeding with direct video summarization (no widget needed)")
                # Skip widget validation and go directly to transcript/metadata retrieval
                widget_info = {
                    'type': 'video',
                    'videoId': video_id,
                    'videoUrl': video_url,
                    'title': f"YouTube Video {video_id}"
                }
            else:
                # Not a video ID/URL, try to get all widgets to show what's available
                try:
                    print(f"[summarize_video_widget] Attempting to get all widgets for error message...")
                    all_widgets = get_all_widgets()
                    print(f"[summarize_video_widget] All widgets retrieved: {len(all_widgets) if all_widgets else 0} widgets")
                    if all_widgets:
                        widget_titles = [w.get('title', 'NO TITLE') for w in all_widgets]
                        print(f"[summarize_video_widget] Available widget titles: {widget_titles}")
                        return f"Widget '{title}' not found. Available widgets: {', '.join(widget_titles)}. Alternatively, you can provide a YouTube URL or video ID to summarize directly."
                    else:
                        print(f"[summarize_video_widget] No widgets found on UI")
                        return f"Widget '{title}' not found. No widgets are currently displayed on the UI. You can provide a YouTube URL or video ID to summarize directly (e.g., 'summarize https://youtube.com/watch?v=VIDEO_ID')."
                except Exception as e:
                    print(f"[summarize_video_widget] Error getting all widgets: {e}")
                    import traceback
                    traceback.print_exc()
                    return f"Widget '{title}' not found. Please check if the widget exists on the UI, or provide a YouTube URL or video ID to summarize directly."
        
        print(f"[summarize_video_widget] Step 2: Checking widget type")
        widget_type = widget_info.get('type')
        print(f"[summarize_video_widget] Widget type: {widget_type}")
        
        if widget_type != 'video':
            print(f"[summarize_video_widget] Step 2 FAILED: Widget is not a video (type: {widget_type})")
            return f"Widget '{title}' is not a video widget (type: {widget_type})."
        
        print(f"[summarize_video_widget] Step 3: Extracting video ID and URL")
        video_id = widget_info.get('videoId')
        video_url = widget_info.get('videoUrl')
        print(f"[summarize_video_widget] Video ID from widget: {video_id}")
        print(f"[summarize_video_widget] Video URL from widget: {video_url}")
        
        if not video_id and not video_url:
            print(f"[summarize_video_widget] Step 3 FAILED: No video ID or URL found")
            return f"Could not find video ID or URL for widget '{title}'"
        
        # Extract video ID if we only have URL
        if not video_id and video_url:
            print(f"[summarize_video_widget] Extracting video ID from URL: {video_url}")
            import re
            match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', video_url)
            if match:
                video_id = match.group(1)
                print(f"[summarize_video_widget] Extracted video ID: {video_id}")
            else:
                print(f"[summarize_video_widget] Step 3 FAILED: Could not extract video ID from URL")
                return f"Could not extract video ID from URL: {video_url}"
        
        print(f"[summarize_video_widget] Step 3 SUCCESS: Final video ID = {video_id}")
        
        # Try to get transcript first - THIS IS REQUIRED FOR SUMMARIZATION
        print(f"[summarize_video_widget] Step 4: Attempting to get transcript")
        transcript = None
        transcript_available = False
        try:
            print(f"[summarize_video_widget] Step 4a: Importing get_transcript function")
            from Functions.YTSummarize import get_transcript
            print(f"[summarize_video_widget] Step 4a SUCCESS: Import successful")
            
            print(f"[summarize_video_widget] Step 4b: Determining transcript URL")
            if video_url:
                transcript_url = video_url
                print(f"[summarize_video_widget] Using video_url: {video_url}")
            elif video_id:
                transcript_url = f"https://www.youtube.com/watch?v={video_id}"
                print(f"[summarize_video_widget] Constructed URL from video_id: {transcript_url}")
            else:
                transcript_url = None
                print(f"[summarize_video_widget] ERROR: No video_url or video_id available")
            
            if transcript_url:
                print(f"[summarize_video_widget] Step 4c: Calling get_transcript with URL: {transcript_url}")
                transcript_result = get_transcript(transcript_url)
                print(f"[summarize_video_widget] Step 4c result: transcript_result type = {type(transcript_result)}, length = {len(str(transcript_result)) if transcript_result else 0}")
            else:
                transcript_result = None
                print(f"[summarize_video_widget] Step 4c SKIPPED: No transcript URL available")
            
            # Validate transcript - must be a valid transcript (not an error message)
            print(f"[summarize_video_widget] Step 4d: Validating transcript result")
            if transcript_result:
                print(f"[summarize_video_widget] Step 4d: transcript_result is not None, type = {type(transcript_result)}")
                if isinstance(transcript_result, str):
                    print(f"[summarize_video_widget] Step 4d: transcript_result is a string, length = {len(transcript_result)}")
                    # Check if it's actually an error message (common error patterns)
                    transcript_lower = transcript_result.lower()
                    print(f"[summarize_video_widget] Step 4d: First 200 chars: {transcript_result[:200]}")
                    
                    error_indicators = [
                        "rate limit", "transcripts are disabled", "cannot provide", 
                        "no transcript found", "connection error", "could not retrieve",
                        "failed to fetch", "blocked", "not available"
                    ]
                    
                    print(f"[summarize_video_widget] Step 4d: Checking for error indicators")
                    is_error = any(indicator in transcript_lower for indicator in error_indicators)
                    print(f"[summarize_video_widget] Step 4d: is_error = {is_error}")
                    
                    is_too_short = len(transcript_result) < 200  # Real transcripts are usually much longer
                    print(f"[summarize_video_widget] Step 4d: is_too_short = {is_too_short} (length = {len(transcript_result)})")
                    
                    starts_with_error = transcript_result.strip().startswith((
                        "This video", "Sir,", "I cannot", "Connection", "Error:", "Failed"
                    ))
                    print(f"[summarize_video_widget] Step 4d: starts_with_error = {starts_with_error}")
                    
                    # If it's clearly an error message, treat as unavailable
                    if is_error or (is_too_short and starts_with_error):
                        print(f"[summarize_video_widget] Step 4d FAILED: Transcript appears to be error: {transcript_result[:150]}")
                        transcript = None
                        transcript_available = False
                    else:
                        # Valid transcript - should be reasonably long
                        print(f"[summarize_video_widget] Step 4d: Checking transcript length >= 200")
                        if len(transcript_result) >= 200:
                            transcript = transcript_result
                            transcript_available = True
                            print(f"[summarize_video_widget] âœ“ Step 4d SUCCESS: VALID TRANSCRIPT RETRIEVED ({len(transcript)} chars) - WILL USE TRANSCRIPT FOR SUMMARY")
                        else:
                            print(f"[summarize_video_widget] Step 4d FAILED: Transcript too short ({len(transcript_result)} chars), treating as unavailable")
                            transcript = None
                            transcript_available = False
                elif isinstance(transcript_result, list):
                    print(f"[summarize_video_widget] Step 4d: transcript_result is a list, length = {len(transcript_result)}")
                    # If it's a list, join it
                    joined_transcript = " ".join(str(item) for item in transcript_result)
                    print(f"[summarize_video_widget] Step 4d: Joined transcript length = {len(joined_transcript)}")
                    if len(joined_transcript) >= 200:
                        transcript = joined_transcript
                        transcript_available = True
                        print(f"[summarize_video_widget] âœ“ Step 4d SUCCESS: VALID TRANSCRIPT FROM LIST ({len(transcript)} chars) - WILL USE TRANSCRIPT FOR SUMMARY")
                    else:
                        print(f"[summarize_video_widget] Step 4d FAILED: Joined transcript too short ({len(joined_transcript)} chars)")
                        transcript = None
                        transcript_available = False
                else:
                    print(f"[summarize_video_widget] Step 4d FAILED: Unexpected transcript_result type: {type(transcript_result)}")
                    transcript = None
                    transcript_available = False
            else:
                print(f"[summarize_video_widget] Step 4d: transcript_result is None or empty")
                transcript = None
                transcript_available = False
                
        except Exception as e:
            print(f"[summarize_video_widget] Step 4 EXCEPTION: Exception getting transcript: {e}")
            import traceback
            traceback.print_exc()
            transcript = None
            transcript_available = False
        
        print(f"[summarize_video_widget] Step 4 SUMMARY: transcript_available = {transcript_available}, transcript length = {len(transcript) if transcript else 0}")
        
        # Only get metadata if transcript is NOT available (for fallback only)
        print(f"[summarize_video_widget] Step 5: Getting metadata (if needed)")
        metadata = None
        if not transcript_available:
            print(f"[summarize_video_widget] Step 5a: Transcript not available - getting metadata for fallback...")
            metadata = get_youtube_video_metadata(video_id)
            print(f"[summarize_video_widget] Step 5a result: metadata = {metadata}")
            if metadata:
                print(f"[summarize_video_widget] Step 5a SUCCESS: Metadata retrieved: title = {metadata.get('title', 'No title')}, description length = {len(metadata.get('description', '')) if metadata.get('description') else 0}")
            else:
                print(f"[summarize_video_widget] Step 5a FAILED: Could not retrieve metadata")
        else:
            print(f"[summarize_video_widget] Step 5 SKIPPED: Using TRANSCRIPT for summarization (metadata not needed)")
        
        # Must have either transcript or metadata
        print(f"[summarize_video_widget] Step 6: Validating we have either transcript or metadata")
        if not transcript_available and not metadata:
            print(f"[summarize_video_widget] Step 6 FAILED: No transcript and no metadata available")
            return f"Cannot summarize: No transcript available and could not retrieve metadata for video {video_id}. The video may not have captions enabled."
        print(f"[summarize_video_widget] Step 6 SUCCESS: Have {'transcript' if transcript_available else 'metadata'} for summarization")
        
        # Generate summary using Groq only
        print(f"[summarize_video_widget] Step 7: Setting up Groq API")
        try:
            from groq import Groq
            CONFIG_FILE = "cache/config.json"
            groq_api_key = _get_api_key_from_config(CONFIG_FILE, "groq_api_key")
            if not groq_api_key:
                print(f"[summarize_video_widget] Step 7 FAILED: Groq API key not configured")
                return "Cannot summarize: Groq API key is not configured in config.json."
            
            def call_groq_direct_ui(message, max_tokens=2048):
                """Call Groq API directly using openai/gpt-oss-120b for fast summarization."""
                try:
                    client = Groq(api_key=groq_api_key)
                    response = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that creates concise summaries."},
                            {"role": "user", "content": message}
                        ],
                        temperature=0.7,
                        max_tokens=max_tokens
                    )
                    
                    if response.choices and response.choices[0].message:
                        return response.choices[0].message.content
                    return None
                except Exception as e:
                    print(f"[summarize_video_widget] Groq direct call failed: {str(e)}")
                    return None
            
            print(f"[summarize_video_widget] Step 7 SUCCESS: Groq helper function ready")
            
            # PRIORITIZE TRANSCRIPT - only use metadata if transcript is unavailable
            print(f"[summarize_video_widget] Step 8: Creating prompt")
            if transcript_available and transcript:
                # Summarize from transcript - THIS IS THE PRIMARY METHOD
                print(f"[summarize_video_widget] Step 8a: Using TRANSCRIPT for summarization ({len(transcript)} chars)")
                
                # Handle long transcripts by chunking - Groq can handle larger chunks
                max_chunk_size = 12000  # Groq can handle large chunks
                transcript_length = len(transcript)
                
                if transcript_length <= max_chunk_size:
                    # Single chunk
                    prompt = f"""Summarize this video transcript using ONLY third grade reading level words (simple, easy words). Extract ONLY the MAIN highlights and key points - skip minor details. Keep descriptions concise for a light read.

OUTPUT FORMAT (REQUIRED):
Clear descriptive title:
Description on a new line here.

Another clear title:
Description on a new line here.

RULES:
- Each point has a CLEAR, UNDERSTANDABLE title that is basically a shorter version of the description - NOT cryptic or vague
- Title should be easy to understand and explain what happened clearly (e.g., 'Bought sick chameleon Bernie' not 'Bernie Bought', 'Lizard won't eat food' not 'Eats Food')
- Title MUST end with a colon (:) symbol
- Title goes on first line, description goes on the NEXT line (not on same line)
- Description = exactly 2 sentences explaining the point in detail - make it clear and easy to understand
- Include ONLY the MAIN highlights and key points - skip minor details and repetitive information
- Focus on the most important events and outcomes
- Points MUST be in chronological order (the order they happened in the video)
- Use ONLY simple, easy words that a third grader can understand
- Replace complex words: discoverâ†’find, utilizeâ†’use, demonstrateâ†’show, acquireâ†’get, contaminatedâ†’dirty
- One blank line between each point
- Output ONLY the formatted points, nothing else

FULL TRANSCRIPT:
{transcript}

Provide the summary in the format above:"""
                
                    print(f"[summarize_video_widget] Step 9: Calling Groq openai/gpt-oss-120b (single chunk)")
                    # Check for cancellation before API call
                    if _is_cancelled(title):
                        print(f"[summarize_video_widget] Cancellation detected before single chunk API call")
                        raise InterruptedError("Summarization cancelled by user")
                    summary = call_groq_direct_ui(prompt, max_tokens=4096)
                else:
                    # Multiple chunks - use parallel processing with Groq (no rate limits!)
                    print(f"[summarize_video_widget] Transcript is long ({transcript_length} chars), chunking...")
                    chunks = []
                    for i in range(0, transcript_length, max_chunk_size):
                        chunks.append(transcript[i:i + max_chunk_size])
                    
                    print(f"[summarize_video_widget] Split into {len(chunks)} chunks")
                    
                    # Parallel processing for Groq (much faster!)
                    print(f"[summarize_video_widget] Processing chunks in parallel with Groq openai/gpt-oss-120b")
                    
                    def summarize_chunk(chunk_idx, chunk):
                        # Check for cancellation before processing chunk
                        if _is_cancelled(title):
                            return (chunk_idx, None)
                        chunk_prompt = f"""Summarize this portion of a video transcript using ONLY third grade reading level words (simple, easy words). 
Extract ONLY the MAIN highlights and key points. Focus on what happened and important details.

Use simple words only. Replace complex words: discoverâ†’find, utilizeâ†’use, demonstrateâ†’show, acquireâ†’get.

TRANSCRIPT PORTION:
{chunk}

Provide a brief summary with the main highlights (not every detail):"""
                        return (chunk_idx, call_groq_direct_ui(chunk_prompt, max_tokens=2048))
                    
                    # Process chunks in parallel
                    chunk_summaries = []
                    with ThreadPoolExecutor(max_workers=min(5, len(chunks))) as executor:
                        future_to_chunk = {executor.submit(summarize_chunk, idx, chunk): (idx, chunk) 
                                          for idx, chunk in enumerate(chunks)}
                        
                        results = {}
                        for future in as_completed(future_to_chunk):
                            # Check for cancellation periodically
                            if _is_cancelled(title):
                                print(f"[summarize_video_widget] Cancellation detected during parallel processing")
                                raise InterruptedError("Summarization cancelled by user")
                            
                            chunk_idx, summary = future.result()
                            if summary:
                                results[chunk_idx] = summary
                    
                    # Sort by chunk index to maintain order
                    chunk_summaries = [results[i] for i in sorted(results.keys()) if i in results]
                    
                    if not chunk_summaries:
                        return "Could not generate summary from chunks."
                    
                    # Final summary
                    combined = "\n\n".join(chunk_summaries)
                    final_prompt = f"""Combine these video summary parts into one summary using ONLY third grade reading level words (simple, easy words). Remove any repeated ideas. Keep ONLY the MAIN highlights and key points - skip minor details. Keep descriptions concise for a light read.

OUTPUT FORMAT (REQUIRED):
Clear descriptive title:
Description on a new line here.

Another clear title:
Description on a new line here.

RULES:
- Each point has a CLEAR, UNDERSTANDABLE title that is basically a shorter version of the description - NOT cryptic or vague
- Title should be easy to understand and explain what happened clearly (e.g., 'Bought sick chameleon Bernie' not 'Bernie Bought', 'Lizard won't eat food' not 'Eats Food')
- Title MUST end with a colon (:) symbol
- Title goes on first line, description goes on the NEXT line (not on same line)
- Description = exactly 2 sentences explaining the point in detail - make it clear and easy to understand
- Include ONLY the MAIN highlights and key points from all chunks - skip minor details
- Focus on the most important events and outcomes
- Use ONLY simple, easy words that a third grader can understand
- Replace complex words: discoverâ†’find, utilizeâ†’use, demonstrateâ†’show, acquireâ†’get, contaminatedâ†’dirty
- One blank line between each point
- Output ONLY the formatted points, nothing else

CHUNK SUMMARIES:
{combined}

Provide the final summary in the format above:"""
                    
                    # Check for cancellation before final summary
                    if _is_cancelled(title):
                        print(f"[summarize_video_widget] Cancellation detected before final summary")
                        raise InterruptedError("Summarization cancelled by user")
                    
                    print(f"[summarize_video_widget] Step 9: Creating final summary from chunks with Groq")
                    summary = call_groq_direct_ui(final_prompt, max_tokens=4096)
                
            elif metadata:
                # Summarize from metadata - ONLY IF TRANSCRIPT IS UNAVAILABLE
                print(f"[summarize_video_widget] âš  Generating summary FROM METADATA (transcript unavailable)")
                metadata_text = f"Title: {metadata.get('title', 'Unknown')}\n"
                if metadata.get('description'):
                    metadata_text += f"Description: {metadata.get('description')}"
                
                prompt = f"""Summarize this video using ONLY third grade reading level words (simple, easy words) based on its metadata. Include ONLY the MAIN highlights and key points. Keep descriptions concise for a light read.

Note: A transcript is not available for this video, so I can only provide a summary based on the title and description.

OUTPUT FORMAT (REQUIRED):
Clear descriptive title:
Description on a new line here.

Another clear title:
Description on a new line here.

RULES:
- Each point has a CLEAR, UNDERSTANDABLE title that is basically a shorter version of the description - NOT cryptic or vague
- Title should be easy to understand and explain what happened clearly (e.g., 'Bought sick chameleon Bernie' not 'Bernie Bought', 'Lizard won't eat food' not 'Eats Food')
- Title MUST end with a colon (:) symbol
- Title goes on first line, description goes on the NEXT line (not on same line)
- Description = exactly 2 sentences explaining the point in detail - make it clear and easy to understand
- Include ONLY the MAIN highlights and key points - skip minor details
- Focus on the most important events and outcomes
- Use ONLY simple, easy words that a third grader can understand
- Replace complex words: discoverâ†’find, utilizeâ†’use, demonstrateâ†’show, acquireâ†’get, contaminatedâ†’dirty
- One blank line between each point
- Output ONLY the formatted points, nothing else

Video Metadata:
{metadata_text}

Provide the summary in the format above:"""
                
                print(f"[summarize_video_widget] Step 9: Calling Groq openai/gpt-oss-120b (metadata)")
                # Check for cancellation before API call
                if _is_cancelled(title):
                    print(f"[summarize_video_widget] Cancellation detected before metadata API call")
                    raise InterruptedError("Summarization cancelled by user")
                summary = call_groq_direct_ui(prompt, max_tokens=2048)
            else:
                return f"I couldn't get a transcript or metadata for video {video_id}. The video may not have captions available or there was an error accessing the video information."
            
            if summary:
                print(f"[summarize_video_widget] Step 9 SUCCESS: Summary generated by provider")
            else:
                print(f"[summarize_video_widget] Step 9 FAILED: No summary from Groq")
            
            # Check for cancellation after summary generation
            if _is_cancelled(title):
                print(f"[summarize_video_widget] Cancellation detected after summary generation")
                raise InterruptedError("Summarization cancelled by user")
            
            print(f"[summarize_video_widget] Step 10: Extracted summary, length = {len(summary) if summary else 0}")
            
            if not summary:
                print(f"[summarize_video_widget] Step 10 FAILED: No summary generated")
                return "Could not generate summary."
            
            # Add note if based on metadata (not transcript)
            if not transcript_available:
                print(f"[summarize_video_widget] Step 10: Adding metadata note to summary")
                summary = f"{summary}\n\n(Note: Summary based on video metadata - transcript not available)"
            else:
                # Confirm we're using transcript
                print(f"[summarize_video_widget] âœ“ Step 10 SUCCESS: Summary generated from transcript")
            
            # Check for cancellation before creating widget
            if _is_cancelled(title):
                print(f"[summarize_video_widget] Cancellation detected before widget creation")
                raise InterruptedError("Summarization cancelled by user")
            
            # Create a text widget with the summary
            print(f"[summarize_video_widget] Step 11: Creating text widget")
            try:
                # Use different title based on whether transcript or metadata was used
                if transcript_available:
                    widget_title = f"{title} SUMMARY"
                else:
                    widget_title = f"{title} - METADATA ANALYSIS"
                print(f"[summarize_video_widget] Step 11a: Widget title = '{widget_title}'")
                print(f"[summarize_video_widget] Step 11b: Calling create_text_widget...")
                create_text_widget(summary, widget_title)
                print(f"[summarize_video_widget] âœ“ Step 11 SUCCESS: Widget created")
                
                # Update indicator to check icon only after summary widget is fully created
                try:
                    print(f"[summarize_video_widget] Step 12: Updating transcript indicator to check icon")
                    eel.updateTranscriptIndicator(title, 'complete')()
                except Exception as e:
                    print(f"[summarize_video_widget] Could not update indicator to complete: {e}")
                
                print(f"[summarize_video_widget] ====== SUMMARIZATION COMPLETE ======")
                return f"Summary created in widget '{widget_title}'"
            except Exception as e:
                print(f"[summarize_video_widget] Step 11 FAILED: Error creating widget: {e}")
                import traceback
                traceback.print_exc()
                # Return the summary anyway even if widget creation fails
                print(f"[summarize_video_widget] Returning summary text instead of widget")
                return summary
                
        except InterruptedError as e:
            # Cancellation requested by user
            print(f"[summarize_video_widget] Summarization cancelled for '{title}': {e}")
            raise  # Re-raise to be handled by worker
        except Exception as e:
            print(f"[summarize_video_widget] Step 7-11 EXCEPTION: Error generating summary with Groq: {e}")
            import traceback
            traceback.print_exc()
            return f"Error generating summary: {str(e)}"
            
    except Exception as e:
        print(f"[summarize_video_widget] TOP LEVEL EXCEPTION: Error: {e}")
        import traceback
        traceback.print_exc()
        return f"Error summarizing video widget: {str(e)}"

# Note: update_transcript_indicator is called directly from Python to JavaScript
# The JavaScript function updateTranscriptIndicator is exposed via eel

@eel.expose
def summarize_video_widget_from_title(title):
    """Expose summarize_video_widget to eel - queues the request for processing"""
    # Add to queue instead of processing immediately
    _summarization_queue.put(title)
    queue_size = _summarization_queue.qsize()
    print(f"[Summarization Queue] Added '{title}' to queue (Queue size: {queue_size})")
    return f"Video '{title}' added to summarization queue. Position: {queue_size}"

@eel.expose
def cancel_summarization(title):
    """Cancel summarization for a specific video title"""
    try:
        with _summarization_lock:
            _cancellation_flags[title] = True
            print(f"[Cancel Summarization] Cancellation flag set for '{title}'")
        
        # Also try to remove from queue if it hasn't started processing yet
        # Note: This is a best-effort attempt since Queue doesn't support removal
        # The cancellation flag will be checked during processing
        return f"Cancellation requested for '{title}'. If processing has started, it will stop at the next checkpoint."
    except Exception as e:
        print(f"[Cancel Summarization] Error: {e}")
        return f"Error requesting cancellation: {str(e)}"

@eel.expose
def summarize_video_widget_immediate(title):
    """Process summarization immediately (for manual requests, not auto-summarize)"""
    return summarize_video_widget(title)

@eel.expose
def get_widget_by_title(title):
    """Get information about a specific widget by its title (e.g., 'VIDEO 1')"""
    import time
    
    try:
        print(f"[get_widget_by_title] Called from Python with title: '{title}'")
        
        # Try multiple times with small delays to handle timing issues
        max_attempts = 3
        widget = None
        
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    # Small delay between retries
                    time.sleep(0.2)
                    print(f"[get_widget_by_title] Retry attempt {attempt + 1}/{max_attempts}")
                
                widget = eel.getWidgetByTitle(title)()
                
                if widget:
                    print(f"[get_widget_by_title] Found widget: {widget.get('title', 'NO TITLE')} ({widget.get('type', 'unknown')})")
                    break
                else:
                    # If we got None but no exception, the widget might not exist
                    # But try once more in case of timing issues
                    if attempt < max_attempts - 1:
                        continue
                    else:
                        print(f"[get_widget_by_title] No widget found with title '{title}' after {max_attempts} attempts")
                        
            except Exception as e:
                print(f"[get_widget_by_title] Attempt {attempt + 1} failed: {e}")
                if attempt < max_attempts - 1:
                    continue
                else:
                    raise
        
        if widget:
            if widget.get('type') == 'video':
                video_id = widget.get('videoId')
                video_url = widget.get('videoUrl')
                print(f"[get_widget_by_title] Video URL: {video_url}")
                print(f"[get_widget_by_title] Video ID: {video_id}")
                
                # Fetch video metadata
                if video_id:
                    print(f"[get_widget_by_title] Fetching metadata for video {video_id}...")
                    metadata = get_youtube_video_metadata(video_id)
                    if metadata:
                        widget['videoTitle'] = metadata.get('title')
                        widget['videoDescription'] = metadata.get('description')
                        print(f"[get_widget_by_title] Metadata: {metadata.get('title')}")
                    else:
                        print(f"[get_widget_by_title] Could not fetch video metadata")
        
        return widget
    except Exception as e:
        print(f"[get_widget_by_title] Error getting widget by title '{title}': {e}")
        import traceback
        traceback.print_exc()
        return None

@eel.expose
def create_gesture_control_widget(group_id=None):
    """Create a gesture control widget with on/off switch"""
    widget_id = get_next_widget_id()
    # Random position within viewport
    x = random.randint(50, 800)
    y = random.randint(50, 400)
    # Use 'gesture_control' type
    eel.createWidget(widget_id, "GESTURE CONTROL", 'gesture_control', '', x, y, 350, 200, group_id)
    return widget_id

@eel.expose
def toggle_gesture_control():
    """Toggle gesture control on/off"""
    try:
        from Functions.GestureControl import (
            start_gesture_control, stop_gesture_control, is_gesture_control_active
        )
        
        if is_gesture_control_active():
            stop_gesture_control()
            return {"status": "off", "message": "Gesture control turned off"}
        else:
            if start_gesture_control():
                return {"status": "on", "message": "Gesture control turned on"}
            else:
                return {"status": "error", "message": "Failed to start gesture control"}
    except Exception as e:
        error_msg = str(e)
        # Check for NumPy version incompatibility
        if "numpy" in error_msg.lower() and ("2." in error_msg or "incompatibility" in error_msg.lower()):
            return {"status": "error", "message": "NumPy 2.x incompatibility. Run: pip install 'numpy<2'"}
        elif "numpy" in error_msg.lower() or "pandas" in error_msg.lower():
            return {"status": "error", "message": "Compatibility error. Try: pip install 'numpy<2'"}
        return {"status": "error", "message": f"Error: {error_msg[:80]}"}

@eel.expose
def get_gesture_control_status():
    """Get current gesture control status"""
    try:
        from Functions.GestureControl import is_gesture_control_active
        is_active = is_gesture_control_active()
        return {"active": is_active}
    except:
        return {"active": False}

@eel.expose
def show_gesture_control():
    """Start gesture control automatically (no widget needed)"""
    try:
        from Functions.GestureControl import start_gesture_control
        if start_gesture_control():
            print("[UI] Gesture control started automatically")
            return True
        else:
            print("[UI] Failed to start gesture control")
            return False
    except Exception as e:
        print(f"[UI] Error starting gesture control: {e}")
        import traceback
        traceback.print_exc()
        return False
