import cv2
import numpy as np
import pyautogui
import time
import os
import datetime
import json
import wave
import pyaudio
import subprocess
import threading
import streamlit as st
import logging
from PIL import Image
import base64

# Suppress noisy WebSocket closed errors
logging.getLogger('tornado.websocket').setLevel(logging.ERROR)
logging.getLogger('tornado.access').setLevel(logging.ERROR)

# Define colors for the app
COLORS = {
    "primary": "#4287f5",
    "secondary": "#f54242",
    "success": "#42f554",
    "warning": "#f5ce42",
    "background": "#f0f2f6",
    "text": "#262730"
}

class SimpleScreenRecorder:
    def __init__(self, output_dir=None, region=None):
        # Set output directory
        self.output_dir = output_dir or os.path.join(os.getcwd(), "recordings")
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        # Create temp directory
        self.temp_dir = os.path.join(self.output_dir, "temp")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        
        # Settings
        self.resolution = (1280, 720)  # 720p resolution
        self.fps = 30.0  # Default FPS
        self.region = region
        self.recording = False
        self.video_writer = None
        self.audio_frames = []
        self.metadata = {}
        
        # Audio settings
        self.audio_format = pyaudio.paInt16
        self.channels = 2
        self.rate = 44100
        self.chunk = 1024
    
    def set_metadata(self, **kwargs):
        """Set metadata for the recording"""
        self.metadata.update(kwargs)
    
    def start_recording(self):
        """Start recording the screen and audio"""
        if self.recording:
            return False
        
        # Generate filenames
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Use candidate name if available
        if 'candidate_name' in self.metadata and self.metadata['candidate_name']:
            candidate_name = "".join(c if c.isalnum() else "_" for c in self.metadata['candidate_name'])
            base_filename = f"{candidate_name}_interview_{timestamp}"
        else:
            base_filename = f"screen_recording_{timestamp}"
        
        # Define output files
        self.temp_video_path = os.path.join(self.temp_dir, f"{base_filename}_temp.avi")
        self.audio_path = os.path.join(self.output_dir, f"{base_filename}_audio.wav")
        self.video_path = os.path.join(self.output_dir, f"{base_filename}_video.avi")
        
        # Determine dimensions based on region
        if self.region:
            width, height = self.region[2], self.region[3]  # Use the window's width & height
        else:
            width, height = self.resolution  # Use default resolution for full screen
        
        # Initialize video writer with appropriate dimensions
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        self.video_writer = cv2.VideoWriter(
            self.temp_video_path, 
            fourcc, 
            self.fps,
            (width, height),  # Use window dimensions if region is specified
            True
        )
        
        if not self.video_writer.isOpened():
            return False
        
        # Initialize audio recording
        self.audio = pyaudio.PyAudio()
        self.audio_stream = self.audio.open(
            format=self.audio_format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        self.audio_frames = []
        
        # Start recording threads
        self.recording = True
        
        # Start video recording thread
        self.video_thread = threading.Thread(target=self._record_screen)
        self.video_thread.daemon = True
        self.video_thread.start()
        
        # Start audio recording thread
        self.audio_thread = threading.Thread(target=self._record_audio)
        self.audio_thread.daemon = True
        self.audio_thread.start()
        
        # Save metadata
        self.metadata['start_time'] = timestamp
        self.metadata['video_file'] = os.path.basename(self.video_path)
        self.metadata['audio_file'] = os.path.basename(self.audio_path)
        
        return True
    
    def stop_recording(self):
        """Stop the recording of audio and video"""
        if not self.recording:
            return False
        
        # Set flag to stop recording
        self.recording = False
        
        # Wait for threads to finish
        if hasattr(self, 'video_thread') and self.video_thread.is_alive():
            self.video_thread.join(timeout=3.0)
        
        if hasattr(self, 'audio_thread') and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=3.0)
        
        # Release resources
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        # Stop audio stream
        if hasattr(self, 'audio_stream'):
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio.terminate()
        
        # Save audio to WAV file
        if self.audio_frames:
            try:
                with wave.open(self.audio_path, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(self.audio.get_sample_size(self.audio_format))
                    wf.setframerate(self.rate)
                    wf.writeframes(b''.join(self.audio_frames))
            except Exception as e:
                st.error(f"Error saving audio: {e}")
        
        # Save the video file
        try:
            import shutil
            shutil.copy(self.temp_video_path, self.video_path)
            # Clean up temp file
            os.remove(self.temp_video_path)
        except Exception as e:
            st.error(f"Error saving video: {e}")
        
        # Update metadata
        self.metadata['end_time'] = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._save_metadata()
        
        return True
    
    def _record_screen(self):
        """Thread function to record the screen"""
        try:
            frame_interval = 1.0 / self.fps
            last_capture_time = time.time()
            
            while self.recording:
                current_time = time.time()
                elapsed = current_time - last_capture_time
                
                if elapsed >= frame_interval:
                    # Capture the screen
                    if self.region:
                        # For specific window/region capture, use the correct approach
                        try:
                            # First take a full screenshot
                            full_screenshot = pyautogui.screenshot()
                            
                            # Then crop it to the region we want
                            # region format is (left, top, width, height)
                            left, top, width, height = self.region
                            
                            # Crop the image to our region
                            screenshot = full_screenshot.crop((
                                left,               # Left
                                top,                # Top
                                left + width,       # Right
                                top + height        # Bottom
                            ))
                            
                            # Don't resize - keep original window dimensions
                        except Exception as e:
                            print(f"Error capturing region: {e}")
                            # Fallback to full screen if region capture fails
                            screenshot = pyautogui.screenshot()
                    else:
                        # Capture full screen
                        screenshot = pyautogui.screenshot()
                        # Only resize if we're capturing the full screen
                        screenshot = screenshot.resize(self.resolution)
                    
                    # Convert for OpenCV
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    
                    # Write frame
                    self.video_writer.write(frame)
                    last_capture_time = current_time
                else:
                    # Avoid high CPU usage
                    time.sleep(0.001)
                
        except Exception as e:
            print(f"Error in video recording thread: {e}")
            self.recording = False
    
    def _record_audio(self):
        """Thread function for audio recording"""
        try:
            while self.recording:
                # Read audio chunk
                data = self.audio_stream.read(self.chunk, exception_on_overflow=False)
                self.audio_frames.append(data)
                
        except Exception as e:
            print(f"Error in audio recording thread: {e}")
            self.recording = False
    
    def _save_metadata(self):
        """Save metadata to a JSON file"""
        if not self.metadata:
            return
            
        # Create a filename for the metadata
        if 'video_file' in self.metadata:
            base_name = os.path.splitext(self.metadata['video_file'])[0]
            metadata_filename = f"{base_name}_metadata.json"
        else:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            metadata_filename = f"recording_metadata_{timestamp}.json"
        
        metadata_path = os.path.join(self.output_dir, metadata_filename)
        
        try:
            with open(metadata_path, 'w') as f:
                json.dump(self.metadata, f, indent=4)
        except Exception as e:
            print(f"Error saving metadata: {e}")


def get_window_list():
    """Get list of window titles and positions using pyautogui instead of pygetwindow"""
    try:
        # Alternative implementation that doesn't use pygetwindow
        # This is a simplified approach that just gets active window
        import pyautogui
        
        # Get the active window dimensions as a fallback
        screen_width, screen_height = pyautogui.size()
        
        # Create a single entry for the entire screen
        window_list = [
            {
                'title': "Entire Screen",
                'region': (0, 0, screen_width, screen_height)
            }
        ]
        
        # Try to add additional windows if pygetwindow is available
        try:
            import pygetwindow as gw
            windows = gw.getAllWindows()
            
            for window in windows:
                # Skip windows with empty titles or those that aren't visible
                if not window.title or not window.visible:
                    continue
                
                try:
                    # Use a try/except block for each property access
                    left = window.left
                    top = window.top
                    width = window.width
                    height = window.height
                    
                    # Skip windows with invalid dimensions
                    if width <= 0 or height <= 0:
                        continue
                    
                    window_list.append({
                        'title': window.title,
                        'region': (left, top, width, height)
                    })
                except Exception as e:
                    # Skip this window if it has problems with its properties
                    print(f"Error accessing window properties: {e}")
                    continue
                    
        except ImportError:
            # If pygetwindow isn't available, we'll just use the entire screen option
            pass
            
        return window_list
    except Exception as e:
        print(f"Error getting window list: {e}")
        return [{'title': "Entire Screen", 'region': None}]


def load_css():
    """Load custom CSS styles"""
    st.markdown("""
    <style>
        /* Main background and container */
        .main {
            background-color: #121218;
            color: #ffffff;
        }
        .stApp {
            max-width: 1200px;
            margin: 0 auto;
            background-color: #121218;
        }
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        
        /* Typography */
        h1, h2, h3 {
            color: #ffffff;
        }
        p, span, label {
            color: #f0f0f0;
        }
        
        /* Make all containers match the background */
        .info-card, 
        .stTabs [data-baseweb="tab-panel"],
        .stTabs [data-baseweb="tab-list"],
        .stTabs [data-baseweb="tab"] {
            background-color: #121218 !important;
            border: none !important;
            padding: 1rem;
            color: #ffffff;
        }
        
        /* Remove ALL container backgrounds */
        [data-testid="stVerticalBlock"] > div > div {
            background-color: transparent !important;
        }
        
        /* Specific override for column containers */
        [data-testid="column"] {
            background-color: transparent !important;
            border: none !important;
        }
        
        /* Override for all Streamlit containers */
        .element-container, .stTextInput, .stSelectbox, .stButton, .stForm {
            background-color: transparent !important;
        }
        
        /* Form elements */
        .stTextInput>div>div>input, 
        .stTextArea>div>div>textarea {
            border-radius: 5px;
            background-color: #252530;
            color: white;
            border: 1px solid #353545;
        }
        .stTextInput>div>div>input:focus, 
        .stTextArea>div>div>textarea:focus {
            border-color: #454555;
        }
        
        /* Selectbox */
        .stSelectbox>div>div>div {
            border-radius: 5px;
            background-color: #252530;
            color: white;
        }
        
        /* Buttons */
        .stButton>button {
            border-radius: 10px;
            font-weight: bold;
            transition: all 0.3s ease;
            background-color: #353545;
            color: white;
            border: none;
        }
        .stButton>button:hover {
            background-color: #454555;
        }
        
        /* Recording button styles */
        .record-btn {
            background-color: #ef4444;
            color: white;
            padding: 1rem;
            font-size: 1.2rem;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }
        
        /* Recording indicator */
        .recording-pulse {
            display: inline-block;
            width: 20px;
            height: 20px;
            border-radius: 50%;
            background: #ef4444;
            margin-right: 10px;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% {
                box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.7);
            }
            70% {
                box-shadow: 0 0 0 10px rgba(239, 68, 68, 0);
            }
            100% {
                box-shadow: 0 0 0 0 rgba(239, 68, 68, 0);
            }
        }
        
        /* Footer */
        .footer {
            text-align: center;
            margin-top: 2rem;
            color: #a0a0b0;
            font-size: 0.9rem;
        }
        
        /* Recording section */
        .recording-section {
            border-left: 4px solid #3b82f6;
            padding-left: 1rem;
        }
        
        /* Recent recordings */
        .recent-recordings {
            border-radius: 10px;
            padding: 1rem;
            background-color: transparent !important;
        }
        .video-item {
            padding: 1rem;
            border-bottom: 1px solid #252530;
        }
        .video-item:last-child {
            border-bottom: none;
        }
        
        /* Logo styling */
        .logo-container {
            text-align: center;
            margin-bottom: 1rem;
        }
        .header-with-logo {
            display: flex;
            align-items: center;
        }
        .header-with-logo h1 {
            margin-left: 1rem;
        }
        
        /* Custom sidebar styling */
        [data-testid="stSidebar"] {
            background-color: #1e1e28;
            color: white;
        }
        [data-testid="stSidebar"] .stMarkdown h1,
        [data-testid="stSidebar"] .stMarkdown h2,
        [data-testid="stSidebar"] .stMarkdown h3 {
            color: white;
        }
        [data-testid="stSidebar"] .stMarkdown p {
            color: #f0f0f0;
        }
        
        /* Make sidebar headings white */
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
            color: white !important;
        }
        
        /* Make sidebar text light */
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: #f0f0f0 !important;
        }
        
        /* Adjust sidebar buttons to match theme */
        [data-testid="stSidebar"] button {
            background-color: #353545;
            color: white;
            border: none;
        }
        [data-testid="stSidebar"] button:hover {
            background-color: #454555;
        }
        
        /* Main content areas */
        [data-testid="stVerticalBlock"] {
            background-color: #121218;
            color: white;
        }
        
        /* Status messages */
        .stAlert {
            background-color: #252530;
            color: white;
            border: 1px solid #353545;
        }
        
        /* Dark theme adjustments for success/info/warning messages */
        .element-container > .stAlert > div.stAlert {
            background-color: rgba(25, 135, 84, 0.1) !important;
            color: #98f1c7 !important;
        }
        .element-container div[data-baseweb="notification"] {
            background-color: #252530 !important;
        }
        
        /* Make form labels lighter */
        .stForm label {
            color: #f0f0f0 !important;
        }
        
        /* Style expander */
        .streamlit-expanderHeader {
            background-color: #252530 !important;
            color: white !important;
        }
        .streamlit-expanderContent {
            background-color: #252530 !important;
            color: white !important;
        }
        
        /* Remove specifically the gray backgrounds from columns */
        [data-testid="column"] > div:first-child {
            background-color: transparent !important;
        }
    </style>
    """, unsafe_allow_html=True)


def display_logo(logo_path=None):
    """Display the logo in the sidebar with a pure black background to match the logo exactly"""
    st.sidebar.markdown("""
    <style>
    .logo-container {
        background-color: #000000;  /* Pure black background to match the logo exactly */
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        display: flex;
        justify-content: center;
        align-items: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
    }
    .logo-image {
        width: 100%;
        height: auto;
    }
    </style>
    """, unsafe_allow_html=True)
    
    if logo_path and os.path.exists(logo_path):
        try:
            # Display the actual logo image
            logo = Image.open(logo_path)
            
            # Create a container with pure black background
            st.sidebar.markdown('<div class="logo-container">', unsafe_allow_html=True)
            st.sidebar.image(logo, use_container_width=True)
            st.sidebar.markdown('</div>', unsafe_allow_html=True)
        except Exception as e:
            st.sidebar.error(f"Error loading logo: {e}")
    else:
        # Display a placeholder logo with black background
        st.sidebar.markdown("""
        <div style="text-align: center; padding: 1.5rem; background-color: #000000; border-radius: 10px; margin-bottom: 1rem; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);">
            <h3 style="margin: 0; color: white;">Your Logo Here</h3>
            <p style="margin: 0; font-size: 0.8rem; color: #cccccc;">
                Place your logo.png file in the app directory
            </p>
        </div>
        """, unsafe_allow_html=True)


def create_custom_button(label, key, color="#1e88e5", icon=None, is_disabled=False):
    """Create a custom styled button"""
    if is_disabled:
        button_html = f"""
        <button disabled style="
            background-color: #cccccc;
            color: #666666;
            padding: 0.5rem 1rem;
            font-size: 1rem;
            border-radius: 10px;
            border: none;
            width: 100%;
            cursor: not-allowed;
            margin-bottom: 1rem;
            opacity: 0.7;
        ">
            {icon + ' ' if icon else ''}{label}
        </button>
        """
    else:
        button_html = f"""
        <button style="
            background-color: {color};
            color: white;
            padding: 0.5rem 1rem;
            font-size: 1rem;
            border-radius: 10px;
            border: none;
            width: 100%;
            cursor: pointer;
            margin-bottom: 1rem;
            transition: all 0.3s ease;
        " onmouseover="this.style.opacity=0.9" onmouseout="this.style.opacity=1">
            {icon + ' ' if icon else ''}{label}
        </button>
        """
    
    return st.markdown(button_html, unsafe_allow_html=True)


def display_info_card(title, content, icon=None, color="#3b82f6"):
    """Display an information card with title and content"""
    icon_html = f'<i class="{icon}"></i> ' if icon else ''
    
    card_html = f"""
    <div style="
        background-color: white;
        border-left: 4px solid {color};
        border-radius: 5px;
        padding: 1rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    ">
        <h4 style="margin-top: 0; color: {color};">{icon_html}{title}</h4>
        <div>{content}</div>
    </div>
    """
    
    st.markdown(card_html, unsafe_allow_html=True)


def main():
    # Configure Streamlit page
    st.set_page_config(
        page_title="Screen Recorder",
        page_icon="🎥",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Load custom CSS
    load_css()
    
    # Initialize session state
    if 'recorder' not in st.session_state:
        st.session_state.recorder = None
    
    if 'recording' not in st.session_state:
        st.session_state.recording = False
    
    if 'windows_list' not in st.session_state:
        st.session_state.windows_list = get_window_list()
    
    # Logo path - replace with your actual logo path
    logo_path = "logo.png"  # Update this with your logo file path
    
    # Display logo in the sidebar
    display_logo(logo_path)
    
    # Sidebar components
    st.sidebar.title("Settings")
    
    # Output directory in sidebar
    output_dir = st.sidebar.text_input(
        "Save recordings to:", 
        value=st.session_state.get('output_dir', os.path.join(os.getcwd(), "recordings"))
    )
    st.session_state.output_dir = output_dir
    
    # Sidebar information
    st.sidebar.markdown("---")
    st.sidebar.subheader("Recording Information")
    st.sidebar.markdown("""
    - Resolution: 1280x720 (720p)
    - Format: AVI video, WAV audio
    - Frame Rate: 30 FPS
    """)
    
    # Sidebar controls for windows
    if not st.session_state.recording:
        st.sidebar.markdown("---")
        st.sidebar.subheader("Window Selection")
        
        if st.sidebar.button("🔄 Refresh Window List", use_container_width=True):
            with st.spinner("Detecting windows..."):
                st.session_state.windows_list = get_window_list()
                if st.session_state.windows_list:
                    st.sidebar.success(f"Found {len(st.session_state.windows_list)} windows")
                else:
                    st.sidebar.warning("No windows detected")
    
    # Page title with logo
    st.markdown(
        f"""
        <div class="header-with-logo">
            <h1>Screen and Audio Recorder</h1>
        </div>
        """, 
        unsafe_allow_html=True
    )
    
    # Main content area - use columns for layout
    col1, col2 = st.columns([3, 2])
    
    with col1:
        # Interview details card
        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        st.subheader("Interview Details")
        
        with st.form("interview_form"):
            recruiter_name = st.text_input("Recruiter Name")
            candidate_name = st.text_input("Candidate Name")
            position = st.text_input("Position")
            notes = st.text_area("Notes", height=100)
            
            cols = st.columns(2)
            with cols[0]:
                save_info = st.form_submit_button("💾 Save Interview Info", use_container_width=True)
            
            if save_info:
                # Create interview data JSON
                interview_data = {
                    "recruiter_name": recruiter_name,
                    "candidate_name": candidate_name,
                    "position": position,
                    "notes": notes,
                    "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # Save to file
                try:
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    
                    # Create filename
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    candidate_name_safe = "".join(c if c.isalnum() else "_" for c in candidate_name)
                    filename = f"interview_{candidate_name_safe}_{timestamp}.json"
                    
                    # Write to file
                    with open(os.path.join(output_dir, filename), "w") as f:
                        json.dump(interview_data, f, indent=4)
                    st.success(f"Interview information saved to {filename}")
                except Exception as e:
                    st.error(f"Failed to save interview information: {e}")
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # Add debug information to help with window capture
        if not st.session_state.recording:
            st.markdown('<div class="info-card">', unsafe_allow_html=True)
            st.subheader("Window Selection Debug Info")
            
            # Add a way to test the window selection
            if st.button("Test Selected Window Capture"):
                # Get the selected window information
                window_titles = [w['title'] for w in st.session_state.windows_list]
                selected_window = st.session_state.get('selected_window', window_titles[0] if window_titles else "Entire Screen")
                
                # Find the region for this window
                selected_region = None
                for window in st.session_state.windows_list:
                    if window['title'] == selected_window:
                        selected_region = window['region']
                        break
                
                if selected_region:
                    # Test capture with the region
                    try:
                        left, top, width, height = selected_region
                        st.write(f"Testing capture for: {selected_window}")
                        st.write(f"Region: Left={left}, Top={top}, Width={width}, Height={height}")
                        
                        # Capture the region
                        full_screenshot = pyautogui.screenshot()
                        region_screenshot = full_screenshot.crop((
                            left,               # Left
                            top,                # Top
                            left + width,       # Right
                            top + height        # Bottom
                        ))
                        
                        # Display the captured region
                        st.image(region_screenshot, caption=f"Captured: {selected_window}", use_column_width=True)
                    except Exception as e:
                        st.error(f"Error testing window capture: {e}")
                else:
                    st.warning("No region information available for the selected window.")
            
            st.markdown('</div>', unsafe_allow_html=True)
    
    with col2:
        # Recording controls card
        st.markdown('<div class="info-card">', unsafe_allow_html=True)
        st.subheader("Recording Controls")
        
        # Window selection
        if not st.session_state.recording:
            # Window selection options
            window_titles = [w['title'] for w in st.session_state.windows_list]
            selected_window = st.selectbox("Choose what to record:", window_titles, index=0, key="window_selector")
            # Store the selected window in session_state so we can access it elsewhere
            st.session_state.selected_window = selected_window
            
            # Get the selected region
            selected_region = None
            for window in st.session_state.windows_list:
                if window['title'] == selected_window:
                    selected_region = window['region']
                    if selected_window != "Entire Screen":
                        st.info(f"Will record window: {selected_window}")
                        # Display region details for debugging
                        if selected_region:
                            left, top, width, height = selected_region
                            st.caption(f"Window position: Left={left}, Top={top}, Width={width}, Height={height}")
                    break
        
        # Status indicator
        if st.session_state.recording:
            st.markdown("""
            <div style="
                background-color: #fee2e2;
                border-radius: 10px;
                padding: 1rem;
                margin: 1rem 0;
                display: flex;
                align-items: center;
            ">
                <div class="recording-pulse"></div>
                <span style="font-weight: bold; color: #ef4444;">RECORDING IN PROGRESS</span>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("⏹️ STOP RECORDING", key="stop_btn", use_container_width=True):
                with st.spinner("Processing recording..."):
                    if st.session_state.recorder:
                        st.session_state.recorder.stop_recording()
                
                st.session_state.recording = False
                st.success("Recording completed successfully!")
                st.rerun()
        else:
            st.markdown("""
            <div style="
                background-color: #e0f2fe;
                border-radius: 10px;
                padding: 1rem;
                margin: 1rem 0;
                display: flex;
                align-items: center;
            ">
                <span style="width: 20px; height: 20px; background-color: #3b82f6; border-radius: 50%; margin-right: 10px;"></span>
                <span style="font-weight: bold; color: #3b82f6;">Ready to record</span>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("🎬 START RECORDING", key="start_btn", use_container_width=True):
                # Create recorder
                st.session_state.recorder = SimpleScreenRecorder(
                    output_dir=output_dir,
                    region=selected_region
                )
                
                # Set metadata
                st.session_state.recorder.set_metadata(
                    recruiter_name=recruiter_name,
                    candidate_name=candidate_name,
                    position=position,
                    notes=notes,
                    recording_type="Window: " + selected_window if selected_window != "Entire Screen" else "Entire Screen"
                )
                
                # Countdown
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i in range(5, 0, -1):
                    status_text.info(f"Starting recording in {i}...")
                    progress_bar.progress((5-i)/5)
                    time.sleep(1)
                
                progress_bar.progress(1.0)
                
                # Start recording
                st.session_state.recorder.start_recording()
                st.session_state.recording = True
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Recent recordings section
    st.markdown("---")
    st.subheader("Recent Recordings")
    
    # Create a container with styling for recent recordings
    st.markdown('<div class="recent-recordings">', unsafe_allow_html=True)
    
    if os.path.exists(output_dir):
        # Find video files
        video_files = []
        for file in os.listdir(output_dir):
            if file.endswith('.avi') or file.endswith('.mp4'):
                video_path = os.path.join(output_dir, file)
                mtime = os.path.getmtime(video_path)
                video_files.append({
                    'path': video_path,
                    'name': file,
                    'time': mtime,
                    'date': datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                })
        
        # Sort by time, newest first
        video_files.sort(key=lambda x: x['time'], reverse=True)
        
        # Show the 5 most recent recordings
        if video_files:
            for i, video in enumerate(video_files[:5]):
                st.markdown(f'<div class="video-item">', unsafe_allow_html=True)
                
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"**{video['name']}**")
                with col2:
                    st.markdown(f"Recorded: {video['date']}")
                with col3:
                    st.markdown(f"📁 {os.path.dirname(video['path'])}")
                
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("No recordings found yet.")
    else:
        st.info("Recordings directory does not exist yet. Start recording to create it.")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Footer
    st.markdown("""
    <div class="footer">
        <p>Screen Recorder App © 2025</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()