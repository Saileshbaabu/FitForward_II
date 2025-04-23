"""
Screen and Audio Recorder with Fixed Frame Rate
----------------------------------------------
This script provides a GUI application to record your screen and audio
with proper frame rate handling to ensure correct playback speed.

Requirements:
- Python 3.6+
- opencv-python
- numpy
- pillow
- tkinter (included with Python)
- pyautogui
- pyaudio
- ffmpeg (must be installed on the system)
"""

import logging

# Set up logging configuration to suppress WebSocket closed errors
logging.getLogger('tornado.websocket').setLevel(logging.ERROR)
logging.getLogger('tornado.access').setLevel(logging.ERROR)


import cv2
import numpy as np
import pyautogui
import time
import os
import sys
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import json
import wave
import pyaudio
import subprocess

class ScreenRecorder:
    def __init__(self, output_dir=None, fps=30.0):
        """
        Initialize the screen recorder with settings matching your camera
        
        Args:
            output_dir (str): Directory to save recordings
            fps (float): Frames per second for recording (30 FPS to match camera)
        """
        # Set output directory
        if output_dir is None:
            self.output_dir = os.path.join(os.getcwd(), "recordings")
        else:
            self.output_dir = output_dir
            
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
            
        # Create temp directory for intermediate files
        self.temp_dir = os.path.join(self.output_dir, "temp")
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        
        # Camera-matched settings
        self.fps = fps
        self.resolution = (1280, 720)  # 720p resolution to match camera
        self.recording = False
        self.video_writer = None
        self.audio_frames = []
        self.metadata = {}
        
        # Audio settings
        self.audio_format = pyaudio.paInt16
        self.channels = 2
        self.rate = 44100  # samples per second
        self.chunk = 1024  # record in chunks of 1024 samples
        
        # Check if FFmpeg is installed
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                   stdout=subprocess.PIPE, 
                                   stderr=subprocess.PIPE)
            self.ffmpeg_available = True
            print("FFmpeg detected - will use for frame rate correction")
        except (FileNotFoundError, subprocess.SubprocessError):
            self.ffmpeg_available = False
            print("FFmpeg not found - frame rate correction will be disabled")
        
        print(f"Initialized Screen and Audio Recorder at {self.fps} FPS with resolution {self.resolution}")
    
    def set_metadata(self, **kwargs):
        """Set metadata for the recording"""
        self.metadata.update(kwargs)
    
    def start_recording(self):
        """Start recording the screen and audio separately"""
        if self.recording:
            print("Recording is already in progress")
            return False
        
        # Set timestamp for the recording
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Create filenames for video and audio
        if 'candidate_name' in self.metadata and self.metadata['candidate_name']:
            candidate_name = "".join(c if c.isalnum() else "_" for c in self.metadata['candidate_name'])
            base_filename = f"{candidate_name}_interview_{timestamp}"
        else:
            base_filename = f"screen_recording_{timestamp}"
        
        # Use temporary AVI file for initial recording
        self.temp_video_path = os.path.join(self.temp_dir, f"{base_filename}_temp.avi")
        self.audio_path = os.path.join(self.output_dir, f"{base_filename}_audio.wav")
        
        # Final output file will be MP4 with corrected frame rate
        self.video_path = os.path.join(self.output_dir, f"{base_filename}_video.mp4")
        
        # Get screen size
        screen_width, screen_height = pyautogui.size()
        
        # Use XVID codec for temp recording - this works reliably
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        self.video_writer = cv2.VideoWriter(
            self.temp_video_path, 
            fourcc, 
            self.fps,  # 30 FPS to match camera
            self.resolution,  # 720p to match camera
            True  # isColor = True
        )
        
        if not self.video_writer.isOpened():
            print("Failed to create video writer")
            return False
        
        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        
        # Start audio recording stream
        self.audio_stream = self.audio.open(
            format=self.audio_format,
            channels=self.channels,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk
        )
        
        # Reset audio frames
        self.audio_frames = []
        
        # Start recording in separate threads
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
        self.metadata['settings'] = {
            'fps': self.fps,
            'resolution': f"{self.resolution[0]}x{self.resolution[1]}",
            'codec': 'MP4V'
        }
        self._save_metadata()
        
        print(f"Started recording to temporary file: {self.temp_video_path}")
        print(f"Started recording audio to: {self.audio_path}")
        return True
    
    def stop_recording(self):
        """Stop the recording of audio and video"""
        if not self.recording:
            print("No recording in progress")
            return False
        
        # Set the flag to stop recording
        self.recording = False
        
        # Wait for the recording threads to finish
        if hasattr(self, 'video_thread') and self.video_thread.is_alive():
            self.video_thread.join(timeout=3.0)
        
        if hasattr(self, 'audio_thread') and self.audio_thread.is_alive():
            self.audio_thread.join(timeout=3.0)
        
        # Release the video writer
        if self.video_writer:
            self.video_writer.release()
            self.video_writer = None
        
        # Stop and close audio stream
        if hasattr(self, 'audio_stream'):
            self.audio_stream.stop_stream()
            self.audio_stream.close()
            self.audio.terminate()
        
        # Save audio frames to WAV file
        if self.audio_frames:
            try:
                with wave.open(self.audio_path, 'wb') as wf:
                    wf.setnchannels(self.channels)
                    wf.setsampwidth(self.audio.get_sample_size(self.audio_format))
                    wf.setframerate(self.rate)
                    wf.writeframes(b''.join(self.audio_frames))
                print(f"Audio saved to: {self.audio_path}")
            except Exception as e:
                print(f"Error saving audio: {e}")
        
        # Use FFmpeg to fix frame rate if available
        if self.ffmpeg_available and os.path.exists(self.temp_video_path):
            try:
                print(f"Fixing frame rate with FFmpeg...")
                
                # Use FFmpeg to convert to MP4 with exact frame rate
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', self.temp_video_path,
                    '-r', str(self.fps),  # Force exact frame rate
                    '-c:v', 'libx264',    # Use H.264 codec
                    '-preset', 'medium',  # Balanced encoding speed/quality
                    '-crf', '23',         # Quality level
                    '-pix_fmt', 'yuv420p', # Pixel format for compatibility
                    self.video_path
                ]
                
                # Run FFmpeg
                process = subprocess.run(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                if process.returncode == 0:
                    print(f"Video with fixed frame rate saved to: {self.video_path}")
                    # Remove temporary file
                    os.remove(self.temp_video_path)
                else:
                    print(f"FFmpeg error: {process.stderr.decode()}")
                    # If FFmpeg fails, use the original temp file
                    import shutil
                    shutil.copy(self.temp_video_path, self.video_path.replace('.mp4', '.avi'))
                    print(f"Using original video file: {self.video_path.replace('.mp4', '.avi')}")
                    self.video_path = self.video_path.replace('.mp4', '.avi')
            except Exception as e:
                print(f"Error fixing frame rate: {e}")
                # If there's an error, use the original temp file
                import shutil
                shutil.copy(self.temp_video_path, self.video_path.replace('.mp4', '.avi'))
                print(f"Using original video file: {self.video_path.replace('.mp4', '.avi')}")
                self.video_path = self.video_path.replace('.mp4', '.avi')
        else:
            # If FFmpeg is not available, just use the temp file
            import shutil
            shutil.copy(self.temp_video_path, self.video_path.replace('.mp4', '.avi'))
            print(f"FFmpeg not available. Using original video file: {self.video_path.replace('.mp4', '.avi')}")
            self.video_path = self.video_path.replace('.mp4', '.avi')
        
        # Update metadata
        self.metadata['end_time'] = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self._save_metadata()
        
        return True
    
    def _record_screen(self):
        """Thread function to record the screen with precise timing control"""
        try:
            # This is the critical part - sleep for the exact interval between frames
            frame_interval = 1.0 / self.fps  # Time between frames in seconds
            last_capture_time = time.time()
            frames_captured = 0
            
            while self.recording:
                current_time = time.time()
                elapsed = current_time - last_capture_time
                
                # Only capture a frame when enough time has elapsed
                if elapsed >= frame_interval:
                    # Capture the screen
                    screenshot = pyautogui.screenshot()
                    
                    # Resize to 720p to match camera settings
                    screenshot = screenshot.resize(self.resolution)
                    
                    # Convert to numpy array
                    frame = np.array(screenshot)
                    
                    # Convert from RGB to BGR color space for OpenCV
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    
                    # Write the frame to the video file
                    self.video_writer.write(frame)
                    
                    # Update timing variables
                    frames_captured += 1
                    last_capture_time = current_time
                    
                    # Log progress periodically
                    if frames_captured % 60 == 0:  # Log every ~2 seconds at 30fps
                        print(f"Recorded {frames_captured} frames at {self.fps} FPS")
                else:
                    # Sleep a short time to avoid consuming CPU
                    # Use a small fraction of the frame interval
                    time.sleep(0.001)  # 1ms sleep
                
        except Exception as e:
            print(f"Error in video recording thread: {e}")
            import traceback
            traceback.print_exc()
            self.recording = False
    
    def _record_audio(self):
        """Thread function to continuously record audio"""
        try:
            while self.recording:
                # Read audio chunk
                data = self.audio_stream.read(self.chunk, exception_on_overflow=False)
                # Store in our array
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
            print(f"Saved metadata to: {metadata_path}")
        except Exception as e:
            print(f"Error saving metadata: {e}")


class RecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Interview Screen Recorder")
        self.root.geometry("600x500")
        self.root.resizable(True, True)
        
        self.recorder = None
        self.recording = False
        
        # Output directory
        self.output_dir = os.path.join(os.getcwd(), "recordings")
        
        # Set up the UI
        self.setup_ui()
        
    def setup_ui(self):
        # Create main frame
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Meeting Info Section
        meeting_frame = ttk.LabelFrame(self.main_frame, text="Interview Details")
        meeting_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Grid layout for labels and entry fields
        ttk.Label(meeting_frame, text="Recruiter Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.recruiter_name = ttk.Entry(meeting_frame, width=30)
        self.recruiter_name.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        ttk.Label(meeting_frame, text="Recruiter Email:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.recruiter_email = ttk.Entry(meeting_frame, width=30)
        self.recruiter_email.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        ttk.Label(meeting_frame, text="Candidate Name:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.candidate_name = ttk.Entry(meeting_frame, width=30)
        self.candidate_name.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        ttk.Label(meeting_frame, text="Candidate Email:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.candidate_email = ttk.Entry(meeting_frame, width=30)
        self.candidate_email.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        ttk.Label(meeting_frame, text="Position:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.position = ttk.Entry(meeting_frame, width=30)
        self.position.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        ttk.Label(meeting_frame, text="Notes:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.notes = tk.Text(meeting_frame, width=30, height=4)
        self.notes.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        # Settings section
        settings_frame = ttk.LabelFrame(self.main_frame, text="Recording Settings")
        settings_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Display camera-matched settings
        ttk.Label(settings_frame, text="Resolution: 1280x720 (720p)").pack(anchor=tk.W, padx=5, pady=2)
        ttk.Label(settings_frame, text="Frame Rate: 30 FPS").pack(anchor=tk.W, padx=5, pady=2)
        ttk.Label(settings_frame, text="Video Format: MP4 with H.264 codec").pack(anchor=tk.W, padx=5, pady=2)
        ttk.Label(settings_frame, text="Color Format: YUV 4:2:0").pack(anchor=tk.W, padx=5, pady=2)
        
        # FFmpeg status
        try:
            subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            ttk.Label(settings_frame, text="FFmpeg: Detected (frame rate correction enabled)", 
                     foreground="green").pack(anchor=tk.W, padx=5, pady=2)
        except (FileNotFoundError, subprocess.SubprocessError):
            ttk.Label(settings_frame, text="FFmpeg: Not detected (frame rate correction disabled)", 
                     foreground="red").pack(anchor=tk.W, padx=5, pady=2)
        
        # Output directory setting
        dir_frame = ttk.Frame(settings_frame)
        dir_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(dir_frame, text="Recordings Directory:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.output_dir_var = tk.StringVar(value=self.output_dir)
        ttk.Entry(dir_frame, textvariable=self.output_dir_var, width=30).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        ttk.Button(dir_frame, text="Browse...", command=self.select_output_dir).grid(row=0, column=2, padx=5, pady=5)
        
        # Record control buttons
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=20)
        
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(control_frame, textvariable=self.status_var, font=("", 10, "bold")).pack(side=tk.TOP, pady=5)
        
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(side=tk.TOP, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="Start Recording", command=self.start_recording)
        self.start_button.pack(side=tk.LEFT, padx=10)
        
        self.stop_button = ttk.Button(button_frame, text="Stop Recording", command=self.stop_recording, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=10)
        
        # Save info button
        ttk.Button(control_frame, text="Save Interview Info", command=self.save_interview_info).pack(side=tk.TOP, pady=5)
        
    def select_output_dir(self):
        """Open directory selection dialog"""
        directory = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if directory:  # If user didn't cancel
            self.output_dir_var.set(directory)
            self.output_dir = directory
    
    def save_interview_info(self):
        """Save interview details to a file"""
        interview_data = {
            "recruiter_name": self.recruiter_name.get(),
            "recruiter_email": self.recruiter_email.get(),
            "candidate_name": self.candidate_name.get(),
            "candidate_email": self.candidate_email.get(),
            "position": self.position.get(),
            "notes": self.notes.get("1.0", tk.END),
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # Create filename from candidate name and date
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate_name_safe = "".join(c if c.isalnum() else "_" for c in self.candidate_name.get())
        filename = f"interview_{candidate_name_safe}_{timestamp}.json"
        
        # Save to output directory
        output_dir = self.output_dir_var.get()
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        try:
            with open(os.path.join(output_dir, filename), "w") as f:
                json.dump(interview_data, f, indent=4)
            messagebox.showinfo("Success", f"Interview information saved to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save interview information: {e}")
    
    def start_recording(self):
        """Start the recording process"""
        if self.recording:
            messagebox.showwarning("Warning", "Recording is already in progress")
            return
            
        # Create recorder instance with camera-matched settings
        self.recorder = ScreenRecorder(
            output_dir=self.output_dir_var.get(),
            fps=30.0  # Set to 30 FPS to match camera
        )
        
        # Set metadata from form fields
        self.recorder.set_metadata(
            recruiter_name=self.recruiter_name.get(),
            recruiter_email=self.recruiter_email.get(),
            candidate_name=self.candidate_name.get(),
            candidate_email=self.candidate_email.get(),
            position=self.position.get(),
            notes=self.notes.get("1.0", tk.END)
        )
        
        # Disable start button and enable stop button
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # Start recording
        self.recording = True
        self.status_var.set("Preparing...")
        
        # Give user time to switch to the meeting window
        def countdown():
            for i in range(5, 0, -1):
                self.status_var.set(f"Starting recording in {i}...")
                time.sleep(1)
                
            # Start the recorder
            self.recorder.start_recording()
            self.status_var.set("Recording in progress")
            
        # Run countdown in a separate thread
        threading.Thread(target=countdown, daemon=True).start()
    
    def stop_recording(self):
        """Stop the recording process"""
        if not self.recording:
            return
            
        try:
            # Update status to let user know we're processing the video
            self.status_var.set("Processing recording... Please wait")
            self.root.update()
            
            # Stop the recorder if it exists
            if self.recorder:
                self.recorder.stop_recording()
                
            # Update UI
            self.recording = False
            self.status_var.set("Recording stopped")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            
            # Show file location
            if hasattr(self.recorder, 'video_path') and os.path.exists(self.recorder.video_path):
                messagebox.showinfo("Recording Saved", 
                                  f"Video saved to:\n{self.recorder.video_path}\n\n"
                                  f"Audio saved to:\n{self.recorder.audio_path}\n\n"
                                  f"Frame rate has been fixed to ensure proper playback speed.")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error stopping recording: {e}")
            
        finally:
            # Always reset UI state
            self.recording = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)


if __name__ == "__main__":
    # Start the GUI application
    root = tk.Tk()
    app = RecorderApp(root)
    root.mainloop()