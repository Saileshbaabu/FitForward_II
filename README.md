A comprehensive AI-powered interview analysis system that provides detailed feedback on video interviews by analyzing both visual and audio components.

## Overview

This system helps users improve their interview performance by providing detailed analysis and feedback on their video interviews. It combines computer vision, audio analysis, and natural language processing to deliver comprehensive insights and actionable recommendations.

## Features

- **Video Analysis**
  - Facial expression analysis
  - Body language assessment
  - Eye contact tracking
  - Posture evaluation
  - Professional appearance assessment

- **Audio Analysis**
  - Speech clarity evaluation
  - Voice modulation analysis
  - Pacing and rhythm assessment
  - Filler word detection
  - Speech pattern analysis

- **Comprehensive Reporting**
  - Overall interview score
  - Component-wise performance metrics
  - Detailed strengths and areas for improvement
  - Professional tips and recommendations
  - Personalized improvement plan

- **User-Friendly Interface**
  - Simple video upload process
  - Real-time analysis progress tracking
  - Interactive results display
  - Email report delivery

## Technical Stack

- **Frontend**: Streamlit
- **Backend**: Python
- **AI/ML**: TensorFlow, OpenCV, MediaPipe
- **Audio Processing**: Librosa
- **Video Processing**: FFmpeg, MoviePy
- **Data Analysis**: Pandas, NumPy, Scikit-learn
- **Natural Language Processing**: Custom LLM integration

## Setup Instructions

1. Clone the repository
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up environment variables (see `.env.example`)
4. Ensure FFmpeg is installed on your system
5. Run the application:
   ```bash
   streamlit run app.py
   ```

## Usage

1. Enter your email address for report delivery
2. Upload your interview video (supported formats: MP4, AVI, MOV, MKV)
3. Wait for the analysis to complete
4. Review the results in the web interface
5. Receive a detailed report via email

## Project Structure

- `app.py`: Main application entry point
- `video_analyzer.py`: Video analysis implementation
- `audio_analyzer.py`: Audio analysis implementation
- `llm_analyzer.py`: Natural language processing and feedback generation
- `media_splitter.py`: Video/audio separation utilities
- `email_sender.py`: Email report delivery system
- `combine_interview_analysis.py`: Report generation and combination
- `requirements.txt`: Project dependencies



## Acknowledgments

- FFmpeg for video processing
- TensorFlow and OpenCV for computer vision
- Librosa for audio analysis
- Streamlit for the web interface 
