import streamlit as st
import folium
from streamlit_folium import folium_static, st_folium
from loguru import logger
import os
import requests
import time
import json
import shutil
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from scipy.ndimage import binary_dilation
from moviepy.video.io.ImageSequenceClip import ImageSequenceClip
from moviepy.video.VideoClip import TextClip, ColorClip
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
import zipfile
import base64
from branca.element import Figure, JavascriptLink, CssLink
import sys
import cv2
import io
from streamlit import components

# Configure logger
logger.remove()  # Remove default handler
logger.add(
    "app.log",
    rotation="500 MB",
    retention="10 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
)
logger.add(sys.stderr, level="WARNING")  # Also log warnings and errors to stderr

# Custom theme and styling
st.set_page_config(
    page_title="Historic Aerials Explorer",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* Main container styling */
    .main {
        background-color: #f5f7f9;
    }
    
    /* Card styling */
    div.stExpander {
        background-color: white;
        border-radius: 10px;
        border: 1px solid #e6e9ef;
        padding: 10px;
        margin: 10px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    
    /* Button styling */
    .stButton>button {
        border-radius: 20px;
        padding: 10px 24px;
        font-weight: 500;
    }
    
    /* Progress bar styling */
    div.stProgress > div > div {
        background-color: #4CAF50;
    }
    
    /* Success message styling */
    div.stSuccess {
        padding: 20px;
        border-radius: 10px;
        background-color: #e8f5e9;
        border: 1px solid #4CAF50;
    }
    
    /* Year badge styling */
    .year-badge {
        display: inline-block;
        padding: 4px 8px;
        margin: 2px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 500;
        background-color: #e3f2fd;
        color: #1976d2;
    }
    
    /* Video player container */
    .video-container {
        position: relative;
        width: 100%;
        padding-top: 56.25%; /* 16:9 Aspect Ratio */
    }
    
    .video-container video {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        border-radius: 10px;
    }
    
    /* Timeline styling */
    .timeline {
        display: flex;
        align-items: center;
        margin: 20px 0;
        padding: 10px;
        background-color: #f8f9fa;
        border-radius: 10px;
        overflow-x: auto;
    }
    
    .timeline-point {
        min-width: 80px;
        text-align: center;
        padding: 5px;
        margin: 0 5px;
        border-radius: 15px;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .timeline-point.available {
        background-color: #4CAF50;
        color: white;
    }
    
    .timeline-point.unavailable {
        background-color: #f5f5f5;
        color: #9e9e9e;
    }
</style>
""", unsafe_allow_html=True)

# Constants
OUTPUT_FOLDER = "downloaded_aerial_images"
ARCHIVE_FOLDER = "archived_projects"
CONFIG_FILE = "config.json"

# Create necessary folders
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(ARCHIVE_FOLDER, exist_ok=True)

# Base URL and headers
BASE_URL = "https://tiles.historicaerials.com/"
HEADERS = {
    "Host": "tiles.historicaerials.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Accept": "image/avif,image/webp,image/png,image/svg+xml,image/*;q=0.8,*/*;q=0.5",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Referer": "https://www.historicaerials.com/",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "image",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "same-site",
    "Priority": "u=4, i",
    "Pragma": "no-cache",
}

def get_capabilities():
    """Get information about available WMS layers and services"""
    url = f"{BASE_URL}?service=WMS&request=GetCapabilities&version=1.1.1"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            logger.debug("Successfully retrieved WMS capabilities")
            print(response.text)
            logger.info(response.text)
            return response.text
        logger.warning(f"Failed to get WMS capabilities: {response.status_code}")
    except Exception as e:
        logger.error(f"Error getting WMS capabilities: {e}")
    return None

def get_feature_info(bbox, x, y, layer):
    """Get detailed information about features at a specific location"""
    url = (
        f"{BASE_URL}?service=WMS&request=GetFeatureInfo&layers={layer}"
        f"&query_layers={layer}&info_format=application/json"
        f"&version=1.1.1&width=1&height=1&x={x}&y={y}"
        f"&srs=EPSG:4326&bbox={bbox}"
    )
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            logger.debug(f"Successfully retrieved feature info for layer {layer}")
            return response.json()
        logger.warning(f"Failed to get feature info: {response.status_code}")
    except Exception as e:
        logger.error(f"Error getting feature info: {e}")
    return None

# Aerials list
aerials = [
    [2021, "A"], [2019, "A"], [2017, "A"], [2015, "A"], [2014, "A"],
    [2012, "A"], [2011, "A"], [2010, "A"], [2009, "A"], [2007, "A"],
    [2005, "A"], [2002, "D"], [1999, "D"], [1988, "B"], [1984, "B"],
    [1983, "B"], [1973, "B"], [1972, "B"], [1963, "B"], [1962, "B"],
    [1952, "B"], [1938, "B"]
]

# Custom map click handling JavaScript
MAP_CLICK_JS = """
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Wait for the map to be loaded
    setTimeout(function() {
        var map = document.querySelector('#map');
        if (!map) return;
        
        var mapInstance = map._leaflet;
        if (!mapInstance) return;
        
        // Add click handler
        mapInstance.on('click', function(e) {
            // Send coordinates to Streamlit
            window.parent.postMessage({
                type: 'map_click',
                lat: e.latlng.lat,
                lng: e.latlng.lng
            }, '*');
        });
        
        // Add rectangle update handler
        var rectangle = null;
        mapInstance.on('areaSelect', function(e) {
            if (rectangle) {
                mapInstance.removeLayer(rectangle);
            }
            rectangle = L.rectangle(e.bounds, {
                color: '#ff4444',
                weight: 2,
                fillOpacity: 0.2
            }).addTo(mapInstance);
        });
    }, 1000);
});
</script>
"""

def create_interactive_map(default_location, size_degrees=0.005):
    """Create an interactive map with click handling and bounding box visualization"""
    # Create the map
    m = folium.Map(
        location=default_location,
        zoom_start=15,
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri'
    )
    
    # Add marker and bounding box
    marker = folium.Marker(
        default_location,
        draggable=True,
        popup='Click map or drag me to set location'
    )
    marker.add_to(m)
    
    # Calculate and add bounding box
    half_size = size_degrees / 2
    bounds = [
        [default_location[0] - half_size, default_location[1] - half_size],
        [default_location[0] + half_size, default_location[1] + half_size]
    ]
    folium.Rectangle(
        bounds=bounds,
        color='red',
        weight=2,
        fill=True,
        fill_opacity=0.2,
        popup='Selected Area'
    ).add_to(m)
    
    return m

def check_tile_availability(year, lat, lon, size_degrees):
    """Check if aerial imagery is available for the given location and year"""
    bbox = calculate_bbox(lat, lon, size_degrees)
    
    # First check feature info to get more details about the location
    # feature_info = get_feature_info(bbox, 0, 0, str(year))
    # if feature_info:
    #     logger.debug(f"Feature info for year {year}: {feature_info}")
    
    url = (
        f"{BASE_URL}?service=WMS&request=GetMap&layers={year}&styles=&format=image/jpeg"
        f"&transparent=false&version=1.1.1&width=1&height=1"
        f"&srs=EPSG:4326&bbox={bbox}"
    )
    try:
        response = requests.head(url, headers=HEADERS, timeout=5)
        return response.status_code == 200
    except:
        return False

def get_available_years(lat, lon, size_degrees):
    """Get list of years with available imagery for the location"""
    # Get WMS capabilities first to ensure service is available
    capabilities = get_capabilities()
    if not capabilities:
        logger.warning("Could not retrieve WMS capabilities")
    
    available_years = []
    for year, layer_type in aerials:
        if check_tile_availability(year, lat, lon, size_degrees):
            available_years.append(year)
    return available_years

# Load previous projects if available
def load_config():
    """Load configuration from file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                logger.info("Configuration loaded successfully")
                return config
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return {"projects": [], "favorites": []}
    logger.info("No existing configuration found, creating new")
    return {"projects": [], "favorites": []}

# Save config
def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
            logger.info("Configuration saved successfully")
    except Exception as e:
        logger.error(f"Error saving configuration: {e}")

# Calculate bounding box from center point
def calculate_bbox(center_lat, center_lon, size_degrees=0.005):
    half_size = size_degrees / 2
    minlon = center_lon - half_size
    maxlon = center_lon + half_size
    minlat = center_lat - half_size
    maxlat = center_lat + half_size
    return f"{minlon},{minlat},{maxlon},{maxlat}"

# Download image function
def download_image(year, layer_type, bbox, project_folder, status_placeholder):
    """Downloads an image for the specified year and layer type."""
    logger.info(f"Downloading image for year {year} in project folder {project_folder}")
    url = (
        f"{BASE_URL}?service=WMS&request=GetMap&layers={year}&styles=&format=image/jpeg"
        f"&transparent=false&version=1.1.1&width=512&height=512"
        f"&srs=EPSG:4326&bbox={bbox}"
    )
    try:
        response = requests.get(url, headers=HEADERS, stream=True)
        if response.status_code == 200:
            # Extract project name from folder path
            project_name = os.path.basename(project_folder)
            
            # Use consistent filename pattern
            filename = f"{year}_{project_name}.jpg"
            filepath = os.path.join(project_folder, filename)
            
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            
            # Log the exact path where the file was saved
            logger.info(f"Image saved to: {filepath}")
            status_placeholder.write(f"✅ Downloaded: {filename}")
            logger.success(f"Successfully downloaded image: {filename}")
            return True
        else:
            error_msg = f"Failed to download {year} {layer_type}: {response.status_code}"
            status_placeholder.write(f"❌ {error_msg}")
            logger.error(error_msg)
            return False
    except Exception as e:
        error_msg = f"Error downloading {year} {layer_type}: {e}"
        status_placeholder.write(f"❌ {error_msg}")
        logger.exception(error_msg)
        return False

# Function to reduce watermark
def reduce_watermark(input_path, output_path, status_placeholder):
    """Reduces visibility of white text watermarks with black borders in the image."""
    try:
        # Open the image
        img = Image.open(input_path).convert('RGB')
        img_array = np.array(img)
        
        # Create a mask for white-ish pixels (watermark text)
        white_mask = np.all(img_array > 200, axis=2)
        
        # Create a mask for dark pixels (watermark borders)
        dark_mask = np.all(img_array < 50, axis=2)
        
        # Combine masks to get watermark regions
        watermark_mask = white_mask | dark_mask
        
        # Expand the mask slightly to catch all watermark pixels
        watermark_mask = binary_dilation(watermark_mask, iterations=2)
        
        # For watermarked regions, replace with average of surrounding non-watermarked pixels
        for i in range(img_array.shape[0]):
            for j in range(img_array.shape[1]):
                if watermark_mask[i, j]:
                    # Get surrounding pixels (5x5 window)
                    window_size = 5
                    half = window_size // 2
                    
                    i_start = max(0, i - half)
                    i_end = min(img_array.shape[0], i + half + 1)
                    j_start = max(0, j - half)
                    j_end = min(img_array.shape[1], j + half + 1)
                    
                    # Get non-watermarked pixels in window
                    window = img_array[i_start:i_end, j_start:j_end]
                    window_mask = watermark_mask[i_start:i_end, j_start:j_end]
                    valid_pixels = window[~window_mask]
                    
                    if len(valid_pixels) > 0:
                        # Replace watermarked pixel with median of surrounding non-watermarked pixels
                        img_array[i, j] = np.median(valid_pixels, axis=0)
        
        # Save the processed image
        processed_img = Image.fromarray(img_array)
        processed_img.save(output_path, quality=95)
        return True
    except Exception as e:
        status_placeholder.write(f"❌ Error processing image: {e}")
        return False

# Process all images in a project
def process_all_images(project_folder, status_placeholder):
    """Process all images in the project folder to reduce watermark visibility."""
    logger.info(f"Processing images in project folder: {project_folder}")
    processed_folder = os.path.join(project_folder, "processed")
    os.makedirs(processed_folder, exist_ok=True)
    
    processed_count = 0
    error_count = 0
    
    for year, _ in sorted(aerials, key=lambda x: x[0]):
        input_path = os.path.join(project_folder, f"{year}_{project_folder.split('/')[-1]}.jpg")
        if os.path.exists(input_path):
            output_path = os.path.join(processed_folder, f"{year}_{project_folder.split('/')[-1]}.jpg")
            status_placeholder.write(f"🔄 Processing image for year {year}...")
            logger.debug(f"Processing image for year {year}")
            
            if reduce_watermark(input_path, output_path, status_placeholder):
                processed_count += 1
            else:
                error_count += 1
    
    logger.info(f"Image processing complete. Processed: {processed_count}, Errors: {error_count}")
    return processed_folder

# Create timelapse video
def create_timelapse(project_folder, project_name, status_placeholder, start_year=None, end_year=None, 
                     frame_duration=1.0, use_processed=True, include_years=None):
    """Creates a timelapse video from the downloaded images."""
    logger.info(f"Creating timelapse for project: {project_name}")
    logger.debug(f"Parameters: start_year={start_year}, end_year={end_year}, frame_duration={frame_duration}, use_processed={use_processed}")
    
    # Determine source folder
    processed_folder = os.path.join(project_folder, "processed")
    source_folder = processed_folder if use_processed and os.path.exists(processed_folder) else project_folder
    logger.debug(f"Using source folder: {source_folder}")
    
    # List all files in the directory to help debug
    all_files = os.listdir(source_folder)
    logger.info(f"All files in {source_folder}: {all_files}")
    status_placeholder.write(f"Files in directory: {all_files}")
    
    image_files = []
    years = []
    
    # Sort aerials by year in ascending order
    sorted_aerials = sorted(aerials, key=lambda x: x[0])
    
    # Filter by year range if specified
    if start_year:
        sorted_aerials = [a for a in sorted_aerials if a[0] >= start_year]
    if end_year:
        sorted_aerials = [a for a in sorted_aerials if a[0] <= end_year]
    
    # Filter by specific years if provided
    if include_years:
        sorted_aerials = [a for a in sorted_aerials if a[0] in include_years]
    
    # Find all available images - try multiple filename patterns
    for year, layer_type in sorted_aerials:
        # Try different filename patterns
        possible_patterns = [
            f"{year}_{project_name}.jpg",
            f"{year}_{layer_type}.jpg",
            f"{year}.jpg"
        ]
        
        found = False
        for pattern in possible_patterns:
            image_path = os.path.join(source_folder, pattern)
            logger.info(f"Looking for image at: {image_path}")
            status_placeholder.write(f"Looking for: {pattern}")
            
            if os.path.exists(image_path):
                logger.info(f"Found image: {image_path}")
                image_files.append(image_path)
                years.append(str(year))
                found = True
                break
        
        if not found:
            logger.warning(f"No image found for year {year} with any pattern")
    
    # As a fallback, try to find any image files in the directory
    if not image_files:
        logger.warning("No images found with expected patterns, trying to find any images")
        for file in all_files:
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                try:
                    # Try to extract year from filename
                    parts = file.split('_')
                    if len(parts) > 0:
                        year_str = parts[0]
                        if year_str.isdigit():
                            year = int(year_str)
                            image_path = os.path.join(source_folder, file)
                            image_files.append(image_path)
                            years.append(str(year))
                except:
                    pass
    
    if not image_files:
        error_msg = "No images found to create timelapse"
        status_placeholder.write(f"❌ {error_msg}")
        logger.warning(error_msg)
        return None
    
    status_placeholder.write(f"Processing images for years: {', '.join(years)}")
    logger.info(f"Processing images for years: {', '.join(years)}")
    
    # Create video from image sequence
    try:
        # Create a folder for images with text
        text_images_folder = os.path.join(project_folder, "text_images")
        
        # Add text to images instead of adding text overlays during video creation
        status_placeholder.write("Adding year labels to images...")
        labeled_image_files = add_text_to_images(image_files, years, text_images_folder, status_placeholder)
        
        # Create video from the labeled images
        status_placeholder.write("Generating video from labeled images...")
        base_clip = ImageSequenceClip(labeled_image_files, durations=[frame_duration] * len(labeled_image_files))
        
        # Save video in the project folder with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_filename = f"{project_name}_timelapse_{timestamp}.mp4"
        video_path = os.path.join(project_folder, video_filename)
        base_clip.write_videofile(video_path, fps=24, audio=False)
        
        success_msg = f"Timelapse video created: {video_path}"
        status_placeholder.write(f"✅ {success_msg}")
        logger.success(success_msg)
        return video_path
    except Exception as e:
        error_msg = f"Error creating timelapse: {e}"
        status_placeholder.write(f"❌ {error_msg}")
        logger.exception(error_msg)
        return None

# Function to archive a project
def archive_project(project_folder, config):
    """Archive a project"""
    project_name = os.path.basename(project_folder)
    logger.info(f"Archiving project: {project_name}")
    
    archive_path = os.path.join(ARCHIVE_FOLDER, f"{project_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip")
    
    try:
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(project_folder):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, os.path.dirname(project_folder))
                    zipf.write(file_path, arcname)
        
        # Add to archived projects in config
        project_info = next((p for p in config["projects"] if p["name"] == project_name), None)
        if project_info:
            project_info["archived"] = True
            project_info["archive_path"] = archive_path
            save_config(config)
        
        logger.success(f"Project archived successfully: {archive_path}")
        return archive_path
    except Exception as e:
        logger.exception(f"Error archiving project {project_name}: {e}")
        return None

# Function to create a download link
def get_download_link(file_path, link_text="Download file"):
    with open(file_path, "rb") as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()
    filename = os.path.basename(file_path)
    mime_type = "video/mp4" if file_path.endswith(".mp4") else "application/zip"
    href = f'<a href="data:{mime_type};base64,{b64}" download="{filename}">{link_text}</a>'
    return href

def get_video_html(video_path):
    """Generate HTML for video player with controls"""
    video_base64 = ""
    with open(video_path, "rb") as f:
        video_base64 = base64.b64encode(f.read()).decode()
    
    return f"""
    <div class="video-container">
        <video controls>
            <source src="data:video/mp4;base64,{video_base64}" type="video/mp4">
            Your browser does not support the video tag.
        </video>
    </div>
    """

def render_timeline(available_years, selected_years=None):
    """Render an interactive timeline of available years"""
    timeline_html = '<div class="timeline">'
    
    for year, _ in sorted(aerials, key=lambda x: x[0]):
        css_class = "timeline-point available" if year in available_years else "timeline-point unavailable"
        if selected_years and year in selected_years:
            css_class += " selected"
        
        timeline_html += f'<div class="{css_class}">{year}</div>'
    
    timeline_html += '</div>'
    return timeline_html

def get_year_badges(years):
    """Generate HTML for year badges"""
    badges_html = ""
    for year in sorted(years):
        badges_html += f'<span class="year-badge">{year}</span>'
    return badges_html

def create_text_overlays(years, frame_duration):
    """Creates text overlay clips for each year in the timelapse.
    
    Args:
        years: List of years to create text overlays for
        frame_duration: Duration in seconds for each frame
        
    Returns:
        List of TextClip objects positioned and timed for the video
    """
    text_clips = []
    
    for i, year in enumerate(years):
        try:
            # Try multiple common system fonts
            system_fonts = [
                "C:/Windows/Fonts/Arial.ttf",
                "C:/Windows/Fonts/Verdana.ttf",
                "C:/Windows/Fonts/Tahoma.ttf",
                "C:/Windows/Fonts/Calibri.ttf",
                "C:/Windows/Fonts/Segoe UI.ttf",
                # Add some Mac/Linux system fonts
                "/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/Arial.ttf"
            ]
            
            txt_clip = None
            
            # First try custom font if available
            try:
                font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts', 'Nexa-Heavy.ttf')
                txt_clip = (TextClip(font=font_path, 
                          text=str(year),
                          font_size=30,
                          color='yellow')
                      .set_position(('left', 'bottom'))
                      .set_duration(frame_duration)
                      .set_start(i * frame_duration))
            except Exception as custom_font_error:
                logger.warning(f"Failed to load custom font: {custom_font_error}. Trying system fonts.")
                
                # If custom font fails, try system fonts
                for font in system_fonts:
                    if txt_clip is not None:
                        break
                        
                    try:
                        txt_clip = (TextClip(font=font,
                                  text=str(year), 
                                  font_size=30,
                                  color='yellow')
                              .set_position(('left', 'bottom'))
                              .set_duration(frame_duration)
                              .set_start(i * frame_duration))
                    except Exception as font_error:
                        logger.warning(f"Failed to load font {font}: {font_error}")
                
                # Last resort - try using method='label' which might work without a font
                if txt_clip is None:
                    try:
                        txt_clip = (TextClip(text=str(year), 
                                font_size=30,
                                method='label',
                                color='yellow')
                          .set_position(('left', 'bottom'))
                          .set_duration(frame_duration)
                          .set_start(i * frame_duration))
                    except Exception as label_error:
                        logger.error(f"All font options failed. Last error: {label_error}")
                        # Create a simple ColorClip with no text as a last resort
                        txt_clip = ColorClip(size=(1, 1), color=(0, 0, 0, 0), duration=frame_duration)
            
            if txt_clip is not None:
                text_clips.append(txt_clip)
                
        except Exception as e:
            logger.exception(f"Error creating text overlay for year {year}: {e}")
            # Skip this text clip if there's an error
            
    return text_clips

def add_text_to_images(image_files, years, output_folder, status_placeholder):
    """Adds year text directly to the image files before video creation.
    
    Args:
        image_files: List of image file paths
        years: List of corresponding years for each image
        output_folder: Folder to save processed images with text
        status_placeholder: Streamlit container for status updates
        
    Returns:
        List of paths to new images with text added
    """
    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    processed_image_files = []
    
    # Try to load a font
    font = None
    font_size = 36
    
    # Try multiple fonts
    font_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts', 'Nexa-Heavy.ttf'),
        "C:/Windows/Fonts/Arial.ttf",
        "C:/Windows/Fonts/Verdana.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ]
    
    for path in font_paths:
        try:
            font = ImageFont.truetype(path, font_size)
            logger.info(f"Successfully loaded font: {path}")
            break
        except Exception as e:
            logger.warning(f"Could not load font {path}: {e}")
    
    # If no TrueType fonts are available, use default font
    if font is None:
        try:
            # Try to use PIL's default font
            font = ImageFont.load_default()
            logger.info("Using default font")
        except Exception as e:
            logger.error(f"Could not load any font: {e}")
            # Continue without a font - we'll use OpenCV's putText as fallback
    
    # Process each image
    for i, (image_path, year) in enumerate(zip(image_files, years)):
        try:
            status_placeholder.write(f"Adding text to image {i+1}/{len(image_files)}...")
            output_path = os.path.join(output_folder, f"text_{os.path.basename(image_path)}")
            
            # Try using PIL first (better font support)
            try:
                if font is not None:
                    # Open image with PIL
                    img = Image.open(image_path)
                    draw = ImageDraw.Draw(img)
                    
                    # Get text size for positioning
                    text = str(year)
                    text_width, text_height = draw.textsize(text, font=font)
                    
                    # Position text in bottom left with padding
                    x = 20
                    y = img.height - text_height - 20
                    
                    # Add a semi-transparent background for text
                    rect_padding = 10
                    draw.rectangle(
                        [(x - rect_padding, y - rect_padding), 
                         (x + text_width + rect_padding, y + text_height + rect_padding)],
                        fill=(0, 0, 0, 128)
                    )
                    
                    # Draw text
                    draw.text((x, y), text, font=font, fill=(255, 255, 255))
                    
                    # Save image
                    img.save(output_path)
                    logger.info(f"Added text to image using PIL: {output_path}")
                else:
                    raise Exception("No font available for PIL")
            
            except Exception as pil_error:
                logger.warning(f"PIL text rendering failed: {pil_error}. Falling back to OpenCV.")
                
                # Fallback to OpenCV
                img = cv2.imread(image_path)
                
                # Define text properties
                text = str(year)
                font_face = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 1.2
                font_thickness = 3
                font_color = (255, 255, 255)  # White color in BGR
                
                # Get text size for positioning
                (text_width, text_height), baseline = cv2.getTextSize(
                    text, font_face, font_scale, font_thickness
                )
                
                # Position text in bottom left with padding
                x = 20
                y = img.shape[0] - 20  # 20px from bottom
                
                # Add a semi-transparent background for text
                rect_padding = 10
                overlay = img.copy()
                cv2.rectangle(
                    overlay,
                    (x - rect_padding, y - text_height - rect_padding),
                    (x + text_width + rect_padding, y + rect_padding),
                    (0, 0, 0),  # Black background
                    -1  # Filled rectangle
                )
                
                # Apply transparency
                alpha = 0.6
                img = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)
                
                # Add text
                cv2.putText(
                    img, text, (x, y - baseline), font_face, font_scale, font_color, font_thickness
                )
                
                # Save image
                cv2.imwrite(output_path, img)
                logger.info(f"Added text to image using OpenCV: {output_path}")
            
            # Add to list of processed files
            processed_image_files.append(output_path)
            
        except Exception as e:
            logger.exception(f"Failed to add text to image {image_path}: {e}")
            # Use original image if text addition fails
            processed_image_files.append(image_path)
            status_placeholder.write(f"⚠️ Could not add text to image {i+1}, using original")
    
    return processed_image_files

def create_image_gallery(image_files, years, project_name):
    """Create an HTML gallery of images with download options."""
    if not image_files:
        return "<p>No images available</p>"
    
    # Add CSS for the gallery
    gallery_css = """
    <style>
        .image-gallery {
            margin: 20px 0;
        }
        
        .gallery-controls {
            margin-bottom: 15px;
        }
        
        .gallery-btn {
            padding: 8px 16px;
            background-color: #4CAF50;
            color: white;
            border: none;
            border-radius: 20px;
            cursor: pointer;
            font-weight: 500;
        }
        
        .gallery-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 16px;
            margin-top: 20px;
        }
        
        .gallery-item {
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
            position: relative;
        }
        
        .gallery-item:hover {
            transform: scale(1.05);
            z-index: 1;
        }
        
        .gallery-img-container {
            position: relative;
            padding-top: 100%; /* 1:1 Aspect Ratio */
            overflow: hidden;
        }
        
        .gallery-img-container img {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        
        .gallery-overlay {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            background: rgba(0,0,0,0.7);
            color: white;
            padding: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .gallery-item:hover .gallery-overlay {
            opacity: 1;
        }
        
        .download-btn {
            color: white;
            font-size: 12px;
            background: rgba(76, 175, 80, 0.8);
            padding: 4px 8px;
            border-radius: 12px;
            text-decoration: none;
        }
        
        .download-btn:hover {
            background: rgba(76, 175, 80, 1);
        }
    </style>
    """
    
    gallery_html = f"""
    <div class="image-gallery">
        <h4>Images for {project_name}</h4>
        <div class="gallery-grid">
    """
    
    # Add each image to the gallery
    for i, (image_path, year) in enumerate(zip(image_files, years)):
        try:
            # Create a base64 representation for preview
            with open(image_path, "rb") as img_file:
                img_data = base64.b64encode(img_file.read()).decode()
                
            # Generate HTML for each image tile
            gallery_html += f"""
            <div class="gallery-item" data-year="{year}">
                <div class="gallery-img-container">
                    <img src="data:image/jpeg;base64,{img_data}" alt="Aerial view from {year}" loading="lazy" />
                    <div class="gallery-overlay">
                        <div class="year-badge">{year}</div>
                        <a href="data:image/jpeg;base64,{img_data}" download="{project_name}_{year}.jpg" class="download-btn">
                            <span>Download</span>
                        </a>
                    </div>
                </div>
            </div>
            """
        except Exception as e:
            logger.error(f"Error creating gallery item for {image_path}: {e}")
    
    # Close the gallery div
    gallery_html += """
        </div>
    </div>
    """
    
    return gallery_css + gallery_html

def get_zip_download_link(image_files, years, project_name):
    """Create a download link for a zip file containing all images.
    
    Args:
        image_files: List of image file paths
        years: List of corresponding years for each image
        project_name: Name of the project for zip filename
        
    Returns:
        HTML string with download link
    """
    try:
        # Create a BytesIO object to store the zip file
        zip_buffer = io.BytesIO()
        
        # Create a zip file in the buffer
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for image_path, year in zip(image_files, years):
                # Add each image to the zip with a descriptive filename
                filename = f"{project_name}_{year}.jpg"
                zip_file.write(image_path, arcname=filename)
        
        # Get the value of the BytesIO buffer
        zip_buffer.seek(0)
        zip_data = zip_buffer.getvalue()
        
        # Encode as base64 for download link
        b64 = base64.b64encode(zip_data).decode()
        
        # Create download link
        href = f'<a href="data:application/zip;base64,{b64}" download="{project_name}_images.zip" class="gallery-btn">📥 Download All Images</a>'
        return href
    except Exception as e:
        logger.error(f"Error creating zip download link: {e}")
        return "<p>Error creating download link</p>"

def get_project_images(project_folder, project_name, use_processed=False, use_text_overlaid=True):
    """Get all image files and their years for a project.
    
    Args:
        project_folder: Path to the project folder
        project_name: Name of the project
        use_processed: Whether to use processed images if available
        use_text_overlaid: Whether to use text-overlaid images if available
        
    Returns:
        tuple: (list of image paths, list of corresponding years)
    """
    # Determine source folder based on priority
    text_images_folder = os.path.join(project_folder, "text_images")
    processed_folder = os.path.join(project_folder, "processed")
    
    # Choose folder based on priority: text_overlaid > processed > original
    if use_text_overlaid and os.path.exists(text_images_folder) and len(os.listdir(text_images_folder)) > 0:
        source_folder = text_images_folder
        logger.info(f"Using text-overlaid images from: {text_images_folder}")
    elif use_processed and os.path.exists(processed_folder) and len(os.listdir(processed_folder)) > 0:
        source_folder = processed_folder
        logger.info(f"Using processed images from: {processed_folder}")
    else:
        source_folder = project_folder
        logger.info(f"Using original images from: {project_folder}")
    
    # Get all image files
    image_files = []
    years = []
    
    # Try to find images for all possible years
    for year, layer_type in sorted(aerials, key=lambda x: x[0]):
        # Try different filename patterns, including text-overlaid images
        possible_patterns = []
        
        # Add text-overlaid image patterns
        if source_folder == text_images_folder:
            possible_patterns.extend([
                f"text_{year}_{project_name}.jpg",
                f"text_{year}_{layer_type}.jpg",
                f"text_{year}.jpg"
            ])
        else:
            # Regular image patterns
            possible_patterns.extend([
                f"{year}_{project_name}.jpg",
                f"{year}_{layer_type}.jpg",
                f"{year}.jpg"
            ])
        
        found = False
        for pattern in possible_patterns:
            image_path = os.path.join(source_folder, pattern)
            if os.path.exists(image_path):
                image_files.append(image_path)
                years.append(str(year))
                found = True
                break
        
        # If not found in primary folder, try fallback folders
        if not found and source_folder != project_folder:
            # Try the original folder
            for pattern in [f"{year}_{project_name}.jpg", f"{year}_{layer_type}.jpg", f"{year}.jpg"]:
                image_path = os.path.join(project_folder, pattern)
                if os.path.exists(image_path):
                    image_files.append(image_path)
                    years.append(str(year))
                    found = True
                    break
    
    # As a fallback, find any images with year in filename in the source folder
    if not image_files:
        for file in os.listdir(source_folder):
            if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                try:
                    # Try to extract year from filename, handling text_ prefix
                    base_name = file
                    if file.startswith("text_"):
                        base_name = file[5:]  # Remove "text_" prefix
                    
                    parts = base_name.split('_')
                    if len(parts) > 0:
                        year_str = parts[0]
                        if year_str.isdigit():
                            year = int(year_str)
                            image_path = os.path.join(source_folder, file)
                            image_files.append(image_path)
                            years.append(str(year))
                except Exception as e:
                    logger.warning(f"Could not extract year from filename {file}: {e}")
    
    # If still no images found and using text_images folder, try original folder
    if not image_files and source_folder != project_folder:
        logger.info(f"No images found in {source_folder}, falling back to {project_folder}")
        return get_project_images(project_folder, project_name, False, False)
    
    return image_files, years

# Main app layout
def main():
    # Load config
    config = load_config()
    logger.info("Starting Historic Aerials Explorer application")
    
    st.title("🛰️ Historic Aerials Explorer")
    
    # Sidebar for navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["New Project", "View Past Projects", "Settings"])
    logger.debug(f"Navigated to page: {page}")
    
    if page == "New Project":
        logger.info("Creating new project")
        st.header("Create New Project")
        
        # Project settings at the top
        st.subheader("Project Settings")
        project_name = st.text_input("Project Name", value=f"project_{datetime.now().strftime('%Y%m%d_%H%M')}")
        
        # Initialize video_path in session state if not present
        if 'video_path' not in st.session_state:
            st.session_state.video_path = None
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            # Map for selecting location
            st.subheader("Select Location")
            default_location = [41.851150562, -87.662658691]  # Chicago default
            
            # Initialize session state for map coordinates
            if 'map_coords' not in st.session_state:
                st.session_state.map_coords = default_location
            
            # Create interactive map
            size = st.number_input(
                "Area Size (degrees)",
                min_value=0.001,
                max_value=0.05,
                value=0.005,
                step=0.001,
                format="%.3f",
                help="Controls the size of the area to capture. Smaller values mean more detailed/zoomed-in imagery."
            )
            
            # Create and display map
            m = create_interactive_map(st.session_state.map_coords, size)
            map_data = st_folium(m, width=800, height=500)
            
            # Handle map click events
            if map_data['last_clicked']:
                st.session_state.map_coords = [
                    map_data['last_clicked']['lat'],
                    map_data['last_clicked']['lng']
                ]
            
            st.info("ℹ️ Click anywhere on the map or drag the marker to select your location of interest.")
            
            # Display coordinates
            lat, lon = st.session_state.map_coords
            col_lat, col_lon = st.columns(2)
            with col_lat:
                st.write(f"**Latitude:** {lat:.8f}")
            with col_lon:
                st.write(f"**Longitude:** {lon:.8f}")
            
            # Preview the video if available
            if st.session_state.video_path and os.path.exists(st.session_state.video_path):
                st.markdown("### Video Preview")
                st.markdown(get_video_html(st.session_state.video_path), unsafe_allow_html=True)
                st.markdown(get_download_link(st.session_state.video_path, "📥 Download Timelapse Video"), unsafe_allow_html=True)
        
        with col2:
            # Advanced options
            st.subheader("Advanced Options")
            image_quality = st.select_slider("Image Quality", options=["Low", "Medium", "High"], value="Medium")
            image_sizes = {"Low": 512, "Medium": 1024, "High": 2048}
            image_size = image_sizes[image_quality]
            
            reduce_watermarks = st.checkbox("Reduce Watermarks", value=False)
            frame_duration = st.slider("Frame Duration (seconds)", min_value=0.5, max_value=5.0, value=1.0, step=0.5)
            reverse_order = st.checkbox("Reverse Chronological Order")
            
            # Start processing button
            if st.button("Start Processing", type="primary"):
                if not project_name:
                    st.error("Please enter a project name")
                else:
                    # Check available years
                    with st.spinner("Checking available imagery..."):
                        available_years = get_available_years(lat, lon, size)
                    
                    if not available_years:
                        st.error("No aerial imagery available for this location. Try a different location or adjust the area size.")
                    else:
                        st.success(f"Found {len(available_years)} years with available imagery!")
                        
                        # Create project folder
                        project_folder = os.path.join(OUTPUT_FOLDER, project_name)
                        os.makedirs(project_folder, exist_ok=True)
                        
                        # Calculate bbox
                        bbox = calculate_bbox(lat, lon, size)
                        
                        # Sort years if needed
                        selected_years = available_years
                        if reverse_order:
                            selected_years = sorted(selected_years, reverse=True)
                        else:
                            selected_years = sorted(selected_years)
                        
                        # Save project info
                        project_info = {
                            "name": project_name,
                            "latitude": lat,
                            "longitude": lon,
                            "size": size,
                            "bbox": bbox,
                            "created": datetime.now().isoformat(),
                            "years": selected_years,
                            "archived": False,
                            "videos": []
                        }
                        
                        if project_name not in [p["name"] for p in config["projects"]]:
                            config["projects"].append(project_info)
                        else:
                            # Update existing project
                            for p in config["projects"]:
                                if p["name"] == project_name:
                                    p.update(project_info)
                        
                        save_config(config)
                        
                        # Progress indicators
                        progress_bar = st.progress(0)
                        status = st.empty()
                        
                        # Download selected images
                        total_steps = len(selected_years) + 2  # +1 for processing, +1 for video
                        
                        for i, year in enumerate(selected_years):
                            status.write(f"Downloading {year} imagery...")
                            download_image(year, project_name, bbox, project_folder, status)
                            progress_bar.progress((i + 1) / total_steps)
                            time.sleep(0.1)
                        
                        # Process images if requested
                        if reduce_watermarks:
                            status.write("Reducing watermark visibility...")
                            process_all_images(project_folder, status)
                        
                        # Create text-overlaid versions of all images
                        status.write("Creating labeled versions of all images...")
                        text_images_folder = os.path.join(project_folder, "text_images")
                        downloaded_images, image_years = get_project_images(project_folder, project_name, use_processed=reduce_watermarks, use_text_overlaid=False)
                        if downloaded_images:
                            add_text_to_images(downloaded_images, image_years, text_images_folder, status)
                        
                        progress_bar.progress((len(selected_years) + 1) / total_steps)
                        
                        # Create timelapse
                        status.write("Creating timelapse video...")
                        video_path = create_timelapse(
                            project_folder, 
                            project_name, 
                            status, 
                            use_processed=reduce_watermarks,
                            frame_duration=frame_duration,
                            include_years=selected_years
                        )
                        
                        if video_path:
                            # Store video path in session state
                            st.session_state.video_path = video_path
                            
                            # Update project with video info
                            for p in config["projects"]:
                                if p["name"] == project_name:
                                    if "videos" not in p:
                                        p["videos"] = []
                                    p["videos"].append({
                                        "path": video_path,
                                        "created": datetime.now().isoformat(),
                                        "years": selected_years
                                    })
                            save_config(config)
                        
                        progress_bar.progress(1.0)
                        
                        st.success(f"Project '{project_name}' processing complete!")
                        st.rerun()  # Rerun the app to display the video

    elif page == "View Past Projects":
        st.header("Past Projects")
        
        if not config["projects"]:
            st.info("No projects found. Create a new project to get started!")
        else:
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                filter_archived = st.checkbox("Show Archived Projects")
            with col2:
                sort_by = st.selectbox("Sort by", ["Newest First", "Oldest First", "Alphabetical"])
            
            # Sort projects
            projects = config["projects"]
            if sort_by == "Newest First":
                projects = sorted(projects, key=lambda x: x.get("created", ""), reverse=True)
            elif sort_by == "Oldest First":
                projects = sorted(projects, key=lambda x: x.get("created", ""))
            else:  # Alphabetical
                projects = sorted(projects, key=lambda x: x.get("name", ""))
            
            # Filter archived
            if not filter_archived:
                projects = [p for p in projects if not p.get("archived", False)]
            
            # Display projects
            for project in projects:
                with st.expander(f"📁 {project['name']} ({project.get('created', '').split('T')[0] if 'created' in project else 'Unknown date'})"):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.write(f"**Location:** {project.get('latitude', 'N/A')}, {project.get('longitude', 'N/A')}")
                        
                        # Display available years as badges
                        project_folder = os.path.join(OUTPUT_FOLDER, project['name'])
                        available_years = get_available_years(project['latitude'], project['longitude'], project['size'])
                        
                        
                        # Create tabs for Map, Gallery, and Videos instead of nested expanders
                        tabs = st.tabs(["Map", "Image Gallery", "Video"])
                        
                        # Tab 1: Map
                        with tabs[0]:
                            if 'latitude' in project and 'longitude' in project:
                                m = folium.Map(location=[project['latitude'], project['longitude']], zoom_start=15)
                                folium.Marker([project['latitude'], project['longitude']]).add_to(m)
                                
                                # Add rectangle to show bounds
                                if 'size' in project:
                                    half_size = project['size'] / 2
                                    bounds = [
                                        [project['latitude'] - half_size, project['longitude'] - half_size],
                                        [project['latitude'] + half_size, project['longitude'] + half_size]
                                    ]
                                    folium.Rectangle(bounds=bounds, color='red', fill=True, fill_opacity=0.2).add_to(m)
                                
                                folium_static(m, width=600, height=300)
                        
                        # Tab 2: Image Gallery
                        with tabs[1]:
                            # Get project images - prefer text-overlaid images
                            image_files, image_years = get_project_images(project_folder, project['name'], use_processed=True, use_text_overlaid=True)
                            
                            if image_files:
                                # Add zip download link
                                st.markdown(get_zip_download_link(image_files, image_years, project['name']), unsafe_allow_html=True)
                                
                                # Display the gallery
                                gallery_html = create_image_gallery(image_files, image_years, project['name'])
                                st.components.v1.html(gallery_html, height=800, scrolling=True)
                            else:
                                st.info("No images available for this project")
                        
                        # Tab 3: Video preview
                        with tabs[2]:
                            # Display latest video if available
                            if "videos" in project and project["videos"]:
                                latest_video = project["videos"][-1]
                                video_path = latest_video["path"]
                                if os.path.exists(video_path):
                                    st.markdown("**Latest Timelapse:**", unsafe_allow_html=True)
                                    st.markdown(get_video_html(video_path), unsafe_allow_html=True)
                            else:
                                st.info("No videos created yet for this project")
                    
                    with col2:
                        project_folder = os.path.join(OUTPUT_FOLDER, project['name'])
                        
                        if os.path.exists(project_folder):
                            # Action buttons
                            if st.button("Create New Timelapse", key=f"new_timelapse_{project['name']}"):
                                st.session_state.selected_project = project['name']
                                st.rerun()
                            
                            # Download buttons for videos
                            if "videos" in project and project["videos"]:
                                st.write("**Available Videos:**")
                                for i, video in enumerate(project["videos"]):
                                    video_path = video["path"]
                                    if os.path.exists(video_path):
                                        st.markdown(
                                            f'<div class="video-info">' +
                                            f'<span class="video-date">{video["created"].split("T")[0]}</span><br/>' +
                                            get_year_badges(video["years"]) +
                                            '</div>',
                                            unsafe_allow_html=True
                                        )
                                        st.markdown(get_download_link(
                                            video_path, 
                                            f"📥 Download Video {i+1}"
                                        ), unsafe_allow_html=True)
                            
                            # Archive button
                            if not project.get("archived", False):
                                if st.button("Archive Project", key=f"archive_{project['name']}"):
                                    archive_path = archive_project(project_folder, config)
                                    st.success(f"Project archived!")
                                    st.markdown(get_download_link(archive_path, "📥 Download Archive"), unsafe_allow_html=True)
                                    st.rerun()
                            else:
                                st.info("This project is archived")
                                if "archive_path" in project and os.path.exists(project["archive_path"]):
                                    st.markdown(get_download_link(project["archive_path"], "📥 Download Archive"), unsafe_allow_html=True)
                        else:
                            st.error("Project files not found")
            
            # If a project is selected for new timelapse
            if 'selected_project' in st.session_state:
                project_name = st.session_state.selected_project
                project = next((p for p in config["projects"] if p["name"] == project_name), None)
                
                if project:
                    st.subheader(f"Create New Timelapse for {project_name}")
                    
                    # Find all available years
                    project_folder = os.path.join(OUTPUT_FOLDER, project_name)
                    available_years = get_available_years(project['latitude'], project['longitude'], project['size'])
                    
                    # Display timeline for year selection
                    st.markdown("**Select Years:**", unsafe_allow_html=True)
                    st.markdown(render_timeline(available_years), unsafe_allow_html=True)
                    
                    # Year range slider
                    min_year = min(available_years) if available_years else 1938
                    max_year = max(available_years) if available_years else 2021
                    year_range = st.slider(
                        "Year Range",
                        min_value=min_year,
                        max_value=max_year,
                        value=(min_year, max_year),
                        step=1
                    )
                    
                    # Filter years based on range
                    selected_years = [y for y in available_years if year_range[0] <= y <= year_range[1]]
                    
                    # Display selected years as badges
                    st.markdown("**Selected Years:**", unsafe_allow_html=True)
                    st.markdown(get_year_badges(selected_years), unsafe_allow_html=True)
                    
                    # Use tabs instead of an expander
                    creation_tabs = st.tabs(["Timelapse Settings", "Available Images"])
                    
                    # Tab 1: Timelapse Settings
                    with creation_tabs[0]:
                        # Custom timelapse options
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            frame_duration = st.slider("Frame Duration (seconds)", min_value=0.5, max_value=5.0, value=1.0, step=0.5)
                        
                        with col2:
                            use_processed = st.checkbox("Use Processed Images (reduced watermark)", value=True)
                            reverse_order = st.checkbox("Reverse Chronological Order")
                    
                    # Tab 2: Available Images
                    with creation_tabs[1]:
                        # Get project images and show gallery - prefer text-overlaid images
                        image_files, image_years = get_project_images(project_folder, project_name, use_processed=use_processed, use_text_overlaid=True)
                        
                        if image_files:
                            # Add zip download link
                            st.markdown(get_zip_download_link(
                                [img for img, yr in zip(image_files, image_years) if int(yr) in selected_years],
                                [yr for yr in image_years if int(yr) in selected_years],
                                project_name
                            ), unsafe_allow_html=True)
                            
                            # Display the gallery only for selected years
                            filtered_images = []
                            filtered_years = []
                            for img, yr in zip(image_files, image_years):
                                try:
                                    if int(yr) in selected_years:
                                        filtered_images.append(img)
                                        filtered_years.append(yr)
                                except ValueError:
                                    # Handle case where year might not be a valid integer
                                    pass
                                    
                            if filtered_images:
                                gallery_html = create_image_gallery(filtered_images, filtered_years, project_name)
                                st.components.v1.html(gallery_html, height=800, scrolling=True)
                            else:
                                st.info("No images available for the selected years")
                        else:
                            st.info("No images available for this project")
                    
                    # Move the Generate Timelapse button outside of tabs
                    if st.button("Generate Timelapse", type="primary"):
                        if not selected_years:
                            st.error("Please select at least one year")
                        else:
                            status = st.empty()
                            
                            # Sort years
                            if reverse_order:
                                selected_years = sorted(selected_years, reverse=True)
                            else:
                                selected_years = sorted(selected_years)
                            
                            video_path = create_timelapse(
                                project_folder,
                                project_name,
                                status,
                                frame_duration=frame_duration,
                                use_processed=use_processed,
                                include_years=selected_years
                            )
                            
                            if video_path:
                                # Update project with video info
                                for p in config["projects"]:
                                    if p["name"] == project_name:
                                        if "videos" not in p:
                                            p["videos"] = []
                                        p["videos"].append({
                                            "path": video_path,
                                            "created": datetime.now().isoformat(),
                                            "years": selected_years
                                        })
                                save_config(config)
                                
                                st.success("Timelapse created successfully!")
                                
                                # Display the new video
                                st.markdown("**Preview:**", unsafe_allow_html=True)
                                st.markdown(get_video_html(video_path), unsafe_allow_html=True)
                                st.markdown(get_download_link(video_path, "📥 Download Timelapse Video"), unsafe_allow_html=True)
                    
                    # Clear selection
                    if st.button("Back to Projects List"):
                        del st.session_state.selected_project
                        st.rerun()
    
    elif page == "Settings":
        st.header("Application Settings")
        
        # Storage management
        st.subheader("Storage Management")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Calculate storage usage
            total_size = 0
            for root, _, files in os.walk(OUTPUT_FOLDER):
                total_size += sum(os.path.getsize(os.path.join(root, file)) for file in files)
            
            archive_size = 0
            for root, _, files in os.walk(ARCHIVE_FOLDER):
                archive_size += sum(os.path.getsize(os.path.join(root, file)) for file in files)
            
            st.write(f"**Active Projects Storage:** {total_size / (1024 * 1024):.2f} MB")
            st.write(f"**Archived Projects Storage:** {archive_size / (1024 * 1024):.2f} MB")
            st.write(f"**Total Storage Usage:** {(total_size + archive_size) / (1024 * 1024):.2f} MB")
            
            # Storage cleanup options
            if st.button("Clean Temporary Files"):
                temp_files_count = 0
                for root, _, files in os.walk(OUTPUT_FOLDER):
                    for file in files:
                        if file.endswith(".tmp"):
                            os.remove(os.path.join(root, file))
                            temp_files_count += 1
                
                st.success(f"Removed {temp_files_count} temporary files")
        
        with col2:
            # Archive all projects option
            if st.button("Archive All Projects"):
                archived_count = 0
                for project in config["projects"]:
                    if not project.get("archived", False):
                        project_folder = os.path.join(OUTPUT_FOLDER, project["name"])
                        if os.path.exists(project_folder):
                            archive_path = archive_project(project_folder, config)
                            archived_count += 1
                
                save_config(config)
                st.success(f"Archived {archived_count} projects")
                
            # Reset application
            with st.expander("Reset Application"):
                st.warning("This will delete all projects, archives, and settings. This action cannot be undone.")
                if st.button("Reset Application", key="reset_confirm"):
                    # Clear all folders
                    shutil.rmtree(OUTPUT_FOLDER, ignore_errors=True)
                    shutil.rmtree(ARCHIVE_FOLDER, ignore_errors=True)
                    
                    # Recreate empty folders
                    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
                    os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
                    
                    # Reset config
                    config = {"projects": [], "favorites": []}
                    save_config(config)
                    
                    st.success("Application reset complete")
                    st.rerun()
        
        # Advanced settings
        st.subheader("Advanced Settings")
        
        with st.expander("API Settings"):
            st.info("These settings control how the application communicates with the aerial imagery API.")
            
            user_agent = st.text_input("User Agent", value=HEADERS["User-Agent"])
            if st.button("Update Headers"):
                HEADERS["User-Agent"] = user_agent
                st.success("Headers updated")
        
        with st.expander("Default Settings"):
            default_lat = st.number_input("Default Latitude", value=41.851150562, format="%.8f")
            default_lon = st.number_input("Default Longitude", value=-87.662658691, format="%.8f")
            default_size = st.number_input("Default Area Size", value=0.005, format="%.5f")
            
            if st.button("Save Default Settings"):
                config["defaults"] = {
                    "latitude": default_lat,
                    "longitude": default_lon,
                    "size": default_size
                }
                save_config(config)
                st.success("Default settings saved")
        
        # About and help
        st.subheader("About")
        st.write("""
        **Historic Aerials Explorer** is an application for downloading, processing, and creating timelapse videos from historical aerial imagery.
        
        The application allows you to:
        - Select locations using an interactive map
        - Download aerial imagery from multiple years
        - Process images to reduce watermark visibility
        - Create custom timelapse videos
        - Archive and manage your projects
        """)

# Run the app
if __name__ == "__main__":
    main()
