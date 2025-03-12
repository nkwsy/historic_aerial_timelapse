# Historic Aerials Explorer

An interactive Streamlit application for exploring, downloading, and creating timelapses from historical aerial imagery.

## Features

- **Interactive Map Interface**: Select locations easily using an interactive map
- **Multi-Year Downloads**: Download aerial imagery from various years (1938-2021)
- **Image Processing**: Automatically reduce watermark visibility in downloaded images
- **Custom Timelapse Creation**: Create timelapse videos with adjustable settings
- **Project Management**: Save, archive, and organize your projects
- **Local Storage**: Save all results to your computer for later use

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/historic-aerials-explorer.git
cd historic-aerials-explorer
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
streamlit run app.py
```

## Usage

### Creating a New Project

1. Navigate to the "New Project" tab
2. Select a location by:
   - Dragging the marker on the map, or
   - Entering coordinates manually
3. Enter a project name
4. Select which years to include
5. Adjust advanced options if needed (image quality, watermark reduction, etc.)
6. Click "Start Processing"
7. Once processing is complete, you can download the timelapse video or all project files

### Viewing Past Projects

1. Navigate to the "View Past Projects" tab
2. Browse your saved projects
3. For each project, you can:
   - View its location on a map
   - Download previously created videos
   - Create new timelapses with custom settings
   - Archive the project

### Settings

- Manage storage usage
- Archive all projects
- Reset application data
- Adjust API and default settings

## Project Structure

- `/downloaded_aerial_images`: Main storage for all projects
- `/archived_projects`: Storage for archived projects
- `config.json`: Configuration file storing project information

## Requirements

- Python 3.7+
- Internet connection (for downloading imagery)
- ~500MB disk space (varies based on number of projects)

## License

MIT License