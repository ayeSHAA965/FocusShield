
# Focus Shield – Digital Distraction Monitor

## Project Overview

Focus Shield is a Python-based productivity application designed to help users manage tasks, maintain focus, and reduce digital distractions through focus sessions and application protection.

The application provides a dashboard to manage daily tasks, track focus sessions, and maintain proof of completed work.

## Features

- **User Authentication:** Secure registration and login.
- **Task Management:** Create, manage, and complete tasks.
- **Proof of Completion:** Optionally upload screenshots or images as proof of completed tasks.
- **Focus Timer:** Set timed focus sessions with automatic completion.
- **Application Protection:** Select applications to be monitored during focus sessions.
- **Emergency Unlock:** End an active focus session through a confirmation-based emergency unlock.
- **Session History:** View previous focus sessions and their durations.
- **Emergency Unlock History:** Track emergency unlock activity.
- **Data Persistence:** Store tasks, sessions, and related records using SQLite.

## Technologies Used

- Python
- Flask
- Flask-SQLAlchemy
- Flask-Login
- SQLite
- HTML
- CSS
- JavaScript

## Project Structure

```text
FocusShield/
│
├── app.py
├── config.py
├── focus_shield.py
├── requirements.txt
├── .gitignore
├── README.md
│
├── models/
├── routes/
├── static/
│   ├── css/
│   ├── js/
│   └── uploads/
│
└── templates/
    ├── dashboard.html
    ├── login.html
    └── register.html
```

## Installation and Setup

### 1. Clone the Repository

```bash
git clone YOUR_GITHUB_REPOSITORY_URL
```

### 2. Navigate to the Project Folder

```bash
cd FocusShield
```

### 3. Create a Virtual Environment

```bash
python -m venv venv
```

### 4. Activate the Virtual Environment

Windows:

```bash
venv\Scripts\activate
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Run the Application

```bash
python app.py
```

### 7. Open in Browser

Visit:

http://127.0.0.1:5000

Register an account or log in to access the dashboard.

## Purpose

The purpose of Focus Shield is to encourage productive habits by combining task management, timed focus sessions, proof-based task completion, and application protection in one application.

## Project Status

Developed as part of an internship project.

**Project Name:** Focus Shield – Digital Distraction Monitor
