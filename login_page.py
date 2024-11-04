import streamlit as st
import json
import os
import cv2
import pyautogui
import numpy as np
from PIL import ImageGrab
from datetime import datetime
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection
import firebase_admin
from firebase_admin import credentials, firestore
import io
from PIL import Image
import speedtest
import cv2
import sounddevice as sd
import hashlib
from google.cloud.firestore import DocumentSnapshot
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from transformers import pipeline

# Load Hugging Face pipelines with explicit models
text_generator = pipeline("text-generation", model="gpt2")
classifier = pipeline("sentiment-analysis", model="distilbert-base-uncased-finetuned-sst-2-english")
question_answerer = pipeline("question-answering", model="distilbert-base-cased-distilled-squad")
# Initialize Firebase
cred = credentials.Certificate("C:/Users/user/Downloads/sush_hx_ap/assessment-platfrom-35db5-firebase-adminsdk-k75sl-92e8c570f8.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
# Connect to Firestore
db = firestore.client()

# User data storage
user_data_file = "user_data.json"
assessments_file = "assessments.json"
responses_file = "responses.json"

# Define the user data file
user_data_file = "user_db.json"

# Function to load user data from JSON file
def load_user_data():
    if os.path.exists(user_data_file):
        with open(user_data_file, "r") as file:
            data = json.load(file)
            print("Loaded user data:", data)  # Debugging line
            return data
    return {}
def load_assessments(file_path):
    with open(file_path, 'r') as f:
        return json.load(f) 
# Function to save user data to JSON file
def save_user_data(user_data):
    with open(user_data_file, "w") as file:
        json.dump(user_data, file, indent=4)

# Helper function to hash passwords
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# User data handling functions
def load_user_data(filename='user_db.json'):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_data(user_data, filename='user_db.json'):
    with open(filename, 'w') as f:
        json.dump(user_data, f)
# Registration function
def register_user(username, password, role):
    user_data = load_user_data()
    if username in user_data:
        return False  # Username already exists
    user_data[username] = {'password': hash_password(password), 'role': role}  # Hash the password
    save_user_data(user_data)
    return True

# Login function
def login_user(username, password):
    user_data = load_user_data()
    if username in user_data:
        user_info = user_data[username]
        if 'password' in user_info:
            stored_password_hash = user_info['password']
            provided_password_hash = hash_password(password)  # Hash the provided password
            print(f"Checking password for {username}: stored hash = {stored_password_hash}, provided hash = {provided_password_hash}")  # Debugging output
            if stored_password_hash == provided_password_hash:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = user_info['role']
                return True
    return False

# Initialize session state for user authentication
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'role' not in st.session_state:
    st.session_state.role = ""

# Login Page
def login_page():
    st.title("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if login_user(username, password):
            st.success("Login successful!")
            st.experimental_rerun()  # Reload the app to show the main page
        else:
            st.error("Invalid username or password.")  # Debugging output

def registration_page():
    st.title("Register")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    role = st.selectbox("Select Role", ["Candidate", "Educator"])
    
    if st.button("Register"):
        if username and password:  # Ensure fields are not empty
            if register_user(username, password, role):
                st.success("Registration successful! Please log in.")
                # You can redirect to the login page using a message instead
                st.info("You can now go back to the login page.")
                # Optionally, display a link or button to navigate to the login page
                if st.button("Go to Login"):
                    # Logic to navigate to the login page, possibly by calling the login_page function directly
                    login_page()
            else:
                st.error("Username already exists. Please choose a different username.")
        else:
            st.error("Please fill in all fields.") 



# Load assessments
def load_assessments():
    if os.path.exists(assessments_file):
        with open(assessments_file, "r") as f:
            assessments = json.load(f)
            for title, details in assessments.items():
                # Ensure time_limit is present
                if 'time_limit' not in details:
                    details['time_limit'] = 60  # Set a default if missing
            return assessments
    return {}



def initialize_session_state():
    """Initialize the session state for user login and role."""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = True  # Set to True for demonstration; change as needed
    if 'role' not in st.session_state:
        st.session_state.role = "Candidate"  # Change based on logged-in user role
    if 'username' not in st.session_state:
        st.session_state.username = "John Doe"  # Placeholder username; set upon login

def format_timestamp(timestamp):
    now = datetime.now()
    time_diff = now - timestamp

    if time_diff.total_seconds() < 60:
        return "just now"
    elif time_diff.total_seconds() < 3600:
        minutes = int(time_diff.total_seconds() // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif time_diff.total_seconds() < 86400:
        hours = int(time_diff.total_seconds() // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(time_diff.days)
        return f"{days} day{'s' if days != 1 else ''} ago"

# Real-time listener for notifications
def listen_notifications():
    notifications_ref = db.collection("notifications").where("user_id", "==", st.session_state.user_id)
    def on_snapshot(doc_snapshot, changes, read_time):
        st.session_state.notifications = [doc.to_dict() for doc in doc_snapshot]
        st.experimental_rerun()  # Rerun the app to update notifications in real-time

    # Watch the notifications collection
    notifications_ref.on_snapshot(on_snapshot)
# Fetch scheduled assessments
def fetch_scheduled_assessments():
    assessments_ref = db.collection("schedules").where("status", "==", "active").order_by("scheduled_date").stream()
    return [assessment.to_dict() for assessment in assessments_ref]

# Fetch notifications for the user
def fetch_notifications():
    notifications_ref = db.collection("notifications").where("user_id", "==", st.session_state.user_id).stream()
    return [notification.to_dict() for notification in notifications_ref]
# Helper Functions
def upload_file_to_firebase(image, file_name):
    """Upload a file to Firebase Storage."""
    blob = bucket.blob(file_name)
    blob.upload_from_file(image)
    return blob.public_url

def delete_file_from_firebase(file_url, user_id):
    """Delete a file from Firebase Storage."""
    # Check permissions
    file_metadata = db.collection("user_files").document(file_url).get().to_dict()
    
    if file_metadata and file_metadata.get("user_id") == user_id:
        try:
            blob = bucket.blob(file_url.split("/")[-1])
            blob.delete()
            st.success("Old profile picture deleted successfully.")
        except Exception as e:
            st.error(f"Error deleting old profile picture: {e}")
    else:
        st.error("You do not have permission to delete this file.")
# Format timestamp to relative time
def format_timestamp(timestamp):
    now = datetime.now()
    time_diff = now - timestamp

    if time_diff.total_seconds() < 60:
        return "just now"
    elif time_diff.total_seconds() < 3600:
        minutes = int(time_diff.total_seconds() // 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif time_diff.total_seconds() < 86400:
        hours = int(time_diff.total_seconds() // 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(time_diff.days)
        return f"{days} day{'s' if days != 1 else ''} ago"

# Real-time listener for notifications
def listen_notifications():
    notifications_ref = db.collection("notifications").where("user_id", "==", st.session_state.user_id)
    def on_snapshot(doc_snapshot, changes, read_time):
        st.session_state.notifications = [doc.to_dict() for doc in doc_snapshot]
        st.experimental_rerun()  # Rerun the app to update notifications in real-time

    # Watch the notifications collection
    notifications_ref.on_snapshot(on_snapshot)
# Save assessment data to a file
def save_assessments(assessments):
    with open('assessments.json', 'w') as f:
        json.dump(assessments, f, indent=4)

# Load answers submitted by candidates
def load_answers():
    try:
        with open('answers.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Save answers submitted by candidates
def save_answers(answers):
    with open('answers.json', 'w') as f:
        json.dump(answers, f, indent=4)

# Helper function to format timestamps
def format_timestamp(timestamp):
    return f"{timestamp} ago"  # Replace with actual time formatting

# Firebase upload function placeholder
def upload_file_to_firebase(image_data, file_name):
    # Implement Firebase upload logic here
    return "firebase_url_placeholder"
def candidate_page(assessments):
    # Initialize session state variables
    if 'current_question' not in st.session_state:
        st.session_state.current_question = 0
    if 'answers' not in st.session_state:
        st.session_state.answers = {}
    if 'current_assessment' not in st.session_state:
        st.session_state.current_assessment = None

    st.title("Available Assessments")

    if not assessments:
        st.write("No assessments available at the moment.")
    else:
        selected_assessment = st.selectbox("Choose an assessment", list(assessments.keys()))

        if selected_assessment:
            st.write(f"Assessment: {selected_assessment}")

            # Callback for starting the assessment
            def start_assessment_callback():
                st.session_state.current_question = 0
                st.session_state.answers = {}
                st.session_state.current_assessment = selected_assessment
                st.success(f"Started {selected_assessment}")

            # Button to start assessment using callback
            if st.button("Start Assessment", on_click=start_assessment_callback):
                pass

            # Continue with the assessment only if one is started
            if st.session_state.current_assessment == selected_assessment:
                questions = assessments[selected_assessment].get('questions', [])
                current_question = st.session_state.current_question

                if current_question < len(questions):
                    question_data = questions[current_question]
                    question_text = question_data.get('question', 'Question text not available')
                    st.write(f"Question {current_question + 1}: {question_text}")

                    options = question_data.get('options', [])
                    if options:
                        selected_option = st.radio("Options", options, key=f"question_{current_question}")
                        if selected_option:
                            st.session_state.answers[current_question] = selected_option

                    # Navigation buttons with callbacks to update current question
                    if st.button("Previous") and current_question > 0:
                        st.session_state.current_question -= 1
                    if st.button("Next") and current_question < len(questions) - 1:
                        st.session_state.current_question += 1
                    if st.button("Submit Assessment"):
                        st.success("Assessment submitted successfully!")
                        st.session_state.current_question = 0
                        st.session_state.answers = {}
                        st.session_state.current_assessment = None
                else:
                    st.write("You have completed the assessment.")


def load_notifications():
    notifications_ref = db.collection("notifications").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(5)
    notifications = notifications_ref.stream()
    notifications_list = [notification.to_dict().get("message", "No message") for notification in notifications]
    return notifications_list

# Calculate metrics for assessments
def calculate_metrics(assessments):
    total_assessments = len(assessments)
    active_assessments = sum(1 for assessment in assessments.values() if assessment.get('status') == 'active')
    inactive_assessments = total_assessments - active_assessments
    return total_assessments, active_assessments, inactive_assessments
def generate_pdf_report(detailed_report):
    # Define the PDF file path
    file_path = "report.pdf"

    # Create a PDF canvas
    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter

    # Add a title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(100, height - 50, "Assessment Report")

    # Add table header
    c.setFont("Helvetica-Bold", 12)
    c.drawString(100, height - 100, "Student")
    c.drawString(300, height - 100, "Score")
    c.drawString(400, height - 100, "Status")

    # Add the data
    c.setFont("Helvetica", 12)
    y_position = height - 120
    for index, row in detailed_report.iterrows():
        c.drawString(100, y_position, row['Student'])
        c.drawString(300, y_position, str(row['Score']))
        c.drawString(400, y_position, row['Status'])
        y_position -= 20  # Move down for the next row

    # Save the PDF
    c.save()
    return file_path
def load_assessments():
    try:
        with open('assessment_data.json', 'r') as json_file:
            data = json.load(json_file)
        
        # Create a dictionary for easier access to assessment metrics
        assessment_summary = {}
        for assessment in data.get('assessments', []):
            name = assessment.get('name')
            assessment_summary[name] = {
                "total_attempts": assessment.get('total_attempts', 0),  # Default to 0 if not found
                "average_score": assessment.get('average_score', 0),    # Default to 0 if not found
                "pass_rate": assessment.get('pass_rate', 0)             # Default to 0 if not found
            }
        
        return assessment_summary
    except Exception as e:
        print(f"Error loading assessment data: {e}")
        return {}
def reports_and_analytics():
    st.title("Reports and Analytics")

    # Load assessment data
    assessment_data = load_assessments()
    assessment_names = list(assessment_data.keys())

    # Assessment Results Summary
    st.subheader("Assessment Results Summary")
    for name, metrics in assessment_data.items():
        st.write(f"**{name}**")
        st.write(f"Total Attempts: {metrics['total_attempts']}")
        st.write(f"Average Score: {metrics['average_score']}")
        st.write(f"Pass Rate: {metrics['pass_rate'] * 100:.2f}%")
        st.write("---")

    # Detailed Reports for Individual Assessments
    selected_assessment = st.selectbox("Select Assessment", assessment_names)
    if selected_assessment:
        detailed_report = load_detailed_report(selected_assessment)  # Call the load_detailed_report function
        st.write(f"Detailed report for {selected_assessment} will be displayed here.")
        st.dataframe(detailed_report)  # Display the detailed report data

        # Performance Analytics (Graphs, Charts)
        st.subheader("Performance Analytics")
        # (Include chart code here if needed)

        # Export options
        if st.button("Download Report as PDF"):
            pdf_file = generate_pdf_report(detailed_report)
            with open(pdf_file, "rb") as f:
                st.download_button("Download PDF", data=f, file_name="report.pdf", mime="application/pdf")

    
def display_settings_page():
    st.header("Settings")

    # Load user data from JSON
    user_data = load_user_data()  # Make sure this function is defined
    username = st.session_state.username  # Get the logged-in user's username
    
    # Check if user exists in the loaded data
    if username in user_data:
        user_info = user_data[username]
        
        # Profile Settings Section
        st.subheader("Profile Settings")
        with st.form("profile_settings"):
            name = st.text_input("Name", value=user_info.get("name", ""))
            email = st.text_input("Email", value=user_info.get("email", ""))
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Update Profile"):
                if update_user_profile(username, name, email, password):  # Make sure this function is defined
                    st.success("Profile updated successfully!")
                else:
                    st.error("Profile update failed.")

        # Notification Preferences Section
        st.subheader("Notification Preferences")
        email_notifications = st.checkbox("Email Notifications", value=user_info.get("email_notifications", False))
        push_notifications = st.checkbox("Push Notifications", value=user_info.get("push_notifications", False))
        
        if st.button("Save Preferences"):
            save_notification_preferences(username, email_notifications, push_notifications)  # Define this function
            st.success("Notification preferences saved!")

        # Integrations and API Keys Management Section
        st.subheader("Integrations and API Keys Management")
        st.write("Manage your API keys and integrations here.")
        
        api_key = st.text_input("API Key")
        if st.button("Add API Key"):
            if add_api_key(api_key, username):  # Define this function to associate keys with users
                st.success("API key added successfully!")
            else:
                st.error("API key already exists.")

        # User Account Management Section
        st.subheader("User Account Management")
        if st.button("Deactivate Account"):
            if deactivate_account(username):  # Define this function
                st.warning("Your account has been deactivated.")
                st.session_state.logged_in = False  # Log out the user
                st.experimental_rerun()  # Reload the app to show the login page
        
        if st.button("Delete Account"):
            if delete_account(username):  # Define this function
                st.warning("Your account has been deleted.")
                st.session_state.logged_in = False  # Log out the user
                st.experimental_rerun()  # Reload the app to show the login page

        # Platform Configuration Settings Section
        st.subheader("Platform Configuration Settings")
        theme = st.selectbox("Select Theme", ["Light", "Dark"])
        if st.button("Save Configuration"):
            # Implement logic to save the configuration if needed
            st.success("Platform configuration updated!")
    else:
        st.error("User not found.")  # Handle case where user is not found in the data


# Add the reports_and_analytics function in the main dashboard navigation
def educator_dashboard():
    st.title("Educator Dashboard")
    st.write(f"Welcome, {st.session_state.username}!")

    # Quick links
    st.sidebar.subheader("Quick Links")
    if st.sidebar.button("Create New Assessment"):
        create_assessment(load_assessments())
    if st.sidebar.button("Upload Questions"):
        upload_questions()

    # Main Dashboard Navigation
    menu_options = ["Home", "Assessments", "Reports", "Settings", "Notifications", "Metrics"]
    selected_menu = st.sidebar.selectbox("Navigation", menu_options)

    if selected_menu == "Home":
        st.write("Welcome to the Home page!")
    elif selected_menu == "Assessments":
        manage_assessment()
    elif selected_menu == "Reports":
        reports_and_analytics()  # Call the reports and analytics function
    elif selected_menu == "Settings":
        display_settings_page()
       
    elif selected_menu == "Notifications":
        
        # Load and display notifications in the main content area
        st.subheader("Notifications")
        notifications = load_notifications()
        if notifications:
            for notification in notifications:
                st.write(f"- {notification}")
        else:
            st.write("No notifications available.")
    elif selected_menu == "Metrics":
        # Load and display metrics in the main content area
        st.subheader("Key Metrics")
        assessments = load_assessments()
        total, active, inactive = calculate_metrics(assessments)

        metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
        with metrics_col1:
            st.metric("Total Assessments", total)
        with metrics_col2:
            st.metric("Active Assessments", active)
        with metrics_col3:
            st.metric("Inactive Assessments", inactive)         
# Functionality to upload questions from a CSV file
def upload_questions():
    st.title("Upload Questions")
    uploaded_file = st.file_uploader("Choose a CSV file with questions", type="csv")

    if uploaded_file is not None:
        import pandas as pd
        questions_df = pd.read_csv(uploaded_file)
        assessments = load_assessments()

        for index, row in questions_df.iterrows():
            question_data = {
                "type": row['Type'],  # Ensure your CSV has a 'Type' column
                "text": row['Question'],  # Ensure your CSV has a 'Question' column
                "options": row['Options'].split(';') if 'Options' in row else [],  # Split options by semicolon
                "correct_option": row['Correct_Option'] if 'Correct_Option' in row else None,  # Adjust as per your CSV
            }
            # You can add more attributes based on your CSV structure
            assessments[row['Assessment_Title']] = assessments.get(row['Assessment_Title'], {"questions": []})
            assessments[row['Assessment_Title']]["questions"].append(question_data)

        save_assessments(assessments)
        st.success("Questions uploaded successfully!")
def create_assessment(assessments):
    st.title("Create New Assessment")
    
    # Assessment Information
    assessment_title = st.text_input("Assessment Title", key="assessment_title")
    assessment_description = st.text_area("Assessment Description", key="assessment_description")
   
    time_limit = st.number_input("Time Limit (in minutes)", min_value=1, value=60, key="time_limit")
    difficulty_level = st.selectbox("Difficulty Level", ["Easy", "Medium", "Hard"], key="difficulty_level")
    total_marks = st.number_input("Total Marks", min_value=1, value=100, key="total_marks")
    
    st.subheader("Questions Section")
    
    question_types = ["MCQ", "Descriptive", "Coding"]
    questions_list = []
    
    # Dynamic question adding
    if "questions" not in st.session_state:
        st.session_state.questions = []

    for i, question_data in enumerate(st.session_state.questions):
        question_type = question_data["type"]
        if question_type == "MCQ":
            question_text = st.text_input(f"MCQ Question {i + 1}", value=question_data.get("text", ""), key=f"mcq_question_{i}")
            options = [st.text_input(f"Option {j + 1} for Question {i + 1}", value=question_data.get("options", [""] * 4)[j], key=f"mcq_option_{i}_{j}") for j in range(4)]
            correct_option = st.selectbox(f"Correct Option for Question {i + 1}", options, key=f"mcq_correct_option_{i}")
            st.session_state.questions[i] = {"type": "MCQ", "text": question_text, "options": options, "correct_option": correct_option}
        
        elif question_type == "Descriptive":
            question_text = st.text_input(f"Descriptive Question {i + 1}", value=question_data.get("text", ""), key=f"descriptive_question_{i}")
            answer_guide = st.text_area(f"Answer Guide for Question {i + 1}", value=question_data.get("answer_guide", ""), key=f"answer_guide_{i}")
            min_words = st.number_input(f"Minimum Words for Question {i + 1}", min_value=1, value=100, key=f"min_words_{i}")
            st.session_state.questions[i] = {"type": "Descriptive", "text": question_text, "answer_guide": answer_guide, "min_words": min_words}
        
        elif question_type == "Coding":
            question_text = st.text_input(f"Coding Question {i + 1}", value=question_data.get("text", ""), key=f"coding_question_{i}")
            code_snippet = st.text_area(f"Code for Question {i + 1}", value=question_data.get("code_snippet", ""), key=f"code_snippet_{i}")
            st.session_state.questions[i] = {"type": "Coding", "text": question_text, "code_snippet": code_snippet}
    
    if st.button("Add Question"):
        question_type = st.selectbox("Select Question Type", question_types)
        new_question_data = {"type": question_type, "text": "", "options": [""] * 4}
        st.session_state.questions.append(new_question_data)

    if st.button("Create Assessment"):
        assessments[assessment_title] = {
            "description": assessment_description,
            "time_limit": time_limit,
            "difficulty_level": difficulty_level,
            "total_marks": total_marks,
            "questions": st.session_state.questions
        }
        assessments.append(new_assessment)
        save_assessments(assessments)
        st.success("Assessment created successfully!")
def schedule_assessment():
    st.title("Schedule Assessment")
    # Load existing assessments
    assessments = load_assessments()
    # Use the keys of the assessments dictionary directly for the select box
    assessment_names = list(assessments.keys())
    # Select an existing assessment to schedule
    selected_assessment_title = st.selectbox("Select an Existing Assessment", assessment_names)
    # Get the selected assessment details using the title directly
    selected_assessment = assessments.get(selected_assessment_title)
    if selected_assessment is not None:
        # Use selected_assessment_title directly for the title input field
        assessment_title = st.text_input("Assessment Title", value=selected_assessment_title, key="schedule_assessment_title", disabled=True)
        assessment_description = st.text_area("Assessment Description", value=selected_assessment.get("description", ""), key="schedule_assessment_description")
        # Use .get() to provide a default value if 'time_limit' is missing
        time_limit = st.number_input("Time Limit (in minutes)", min_value=1, value=selected_assessment.get("time_limit", 30), key="schedule_time_limit")
        schedule_date = st.date_input("Schedule Date", value=datetime.today())
        assessment_status = st.selectbox("Status", ["Active", "Inactive"], index=["Active", "Inactive"].index(selected_assessment.get("status", "inactive").capitalize()), key="schedule_status")
        if st.button("Schedule Assessment"):
            # Update selected assessment with scheduled information
            assessments[selected_assessment_title]["description"] = assessment_description
            assessments[selected_assessment_title]["time_limit"] = time_limit
            assessments[selected_assessment_title]["status"] = assessment_status.lower()
            assessments[selected_assessment_title]["scheduled_date"] = schedule_date.isoformat()  # Store as ISO format for consistency
            # Save updated assessments
            save_assessments(assessments)
            st.success("Assessment scheduled successfully!")
    else:
        st.error("Selected assessment not found.")
def manage_assessment():
    st.title("Manage Assessments")
    assessments = load_assessments()
    if assessments:
        selected_assessment = st.selectbox("Select Assessment to Manage", list(assessments.keys()))
        if selected_assessment:
            assessment_details = assessments[selected_assessment]
            st.write("### Assessment Details")
            st.write(f"**Title:** {selected_assessment}")
            st.write(f"**Description:** {assessment_details['description']}")
            
            # Check for 'time_limit' key
            if 'time_limit' in assessment_details:
                st.write(f"**Time Limit:** {assessment_details['time_limit']} minutes")
            else:
                st.write("**Time Limit:** Not specified")
            st.write(f"**Scheduled Date:** {assessment_details.get('scheduled_date', 'Not scheduled')}")
            # Use .get() to prevent KeyError
            st.write(f"**Status:** {assessment_details.get('status', 'Not specified').capitalize()}")
            new_status = st.selectbox("Update Status", ["Active", "Inactive"], index=0 if assessment_details.get('status') == 'active' else 1)
            if st.button("Update Assessment"):
                assessments[selected_assessment]['status'] = new_status.lower()
                save_assessments(assessments)
                st.success("Assessment status updated successfully!")
    else:
        st.write("No assessments found.")


def initialize_session():
    if 'status' not in st.session_state:
        st.session_state['status'] = {"Internet Speed": "Pending", "Camera": "Pending", "Microphone": "Pending"}
    if 'current_question' not in st.session_state:
        st.session_state['current_question'] = 0
    if 'responses' not in st.session_state:
        st.session_state['responses'] = []
    if 'start_time' not in st.session_state:
        st.session_state['start_time'] = datetime.now()
# Main function to run the application
import json

def load_assessments(file_path):
    try:
        with open(file_path, 'r') as file:
            assessments = json.load(file)
        return assessments
    except Exception as e:
        print(f"Error loading assessments: {e}")
        return {}

def main():
    # Initialize session state variables if not already done
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'role' not in st.session_state:
        st.session_state.role = None
    if 'username' not in st.session_state:
        st.session_state.username = ""
    if 'status' not in st.session_state:  # Initialize status key
        st.session_state.status = {}
    
    # Load assessments only if not already loaded
    if 'assessments' not in st.session_state:
        assessments_file = 'assessments.json'  # Update with your path if necessary
        st.session_state.assessments = load_assessments(assessments_file)

    if st.session_state.logged_in:
        if st.session_state.role == "Educator":
            educator_dashboard()
        elif st.session_state.role == "Candidate":
            candidate_page(st.session_state.assessments)  # Pass the loaded assessments
        else:
            st.write("Role not recognized.")
    else:
        option = st.sidebar.selectbox("Choose an option", ["Login", "Register"])
        if option == "Login":
            login_page()
        else:
            registration_page()

if __name__ == "__main__":
    main()  # Start the application