import os
import requests
import time

from moviepy import *
import cv2
import sys
from PIL import Image
import numpy as np
from scipy.ndimage import binary_dilation

# Output folder for downloaded images
OUTPUT_FOLDER = "downloaded_aerial_images"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Base URL and bounding box (adjust as necessary)
BASE_URL = "https://tiles.historicaerials.com/"
# BBOX = "-87.6654052734375,41.8491046861039,-87.65991210937501,41.85319643776675"

# Headers for the requests
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

# Aerials list
aerials = [
    [2021, "A"], [2019, "A"], [2017, "A"], [2015, "A"], [2014, "A"],
    [2012, "A"], [2011, "A"], [2010, "A"], [2009, "A"], [2007, "A"],
    [2005, "A"], [2002, "D"], [1999, "D"], [1988, "B"], [1984, "B"],
    [1983, "B"], [1973, "B"], [1972, "B"], [1963, "B"], [1962, "B"],
    [1952, "B"], [1938, "B"]
]

def calculate_bbox(center_lat, center_lon, size_degrees=0.005):
    """
    Calculates a bounding box given a center point and size.
    Returns bbox string in format: 'minlon,minlat,maxlon,maxlat'
    """
    half_size = size_degrees / 2
    minlon = center_lon - half_size
    maxlon = center_lon + half_size
    minlat = center_lat - half_size
    maxlat = center_lat + half_size
    return f"{minlon},{minlat},{maxlon},{maxlat}"

def create_timelapse(project_folder, project_name):
    """
    Creates a timelapse video from the downloaded images.
    Orders images from oldest to newest with 1-second transitions.
    """
    image_files = []
    years = []
    
    # Sort aerials by year in ascending order
    sorted_aerials = sorted(aerials, key=lambda x: x[0])
    for year, _ in sorted_aerials:
        image_path = os.path.join(project_folder, f"{year}_{project_name}.jpg")
        if os.path.exists(image_path):
            image_files.append(image_path)
            years.append(str(year))
    
    # Debug: Print the order of years being processed
    print("Processing images for years:", years)
    
    if not image_files:
        print("No images found to create timelapse")
        return
    
    # Create video from image sequence
    base_clip = ImageSequenceClip(image_files, durations=[1] * len(image_files))
    
    # Create text clips for each year
    text_clips = []
    for i, year in enumerate(years):
        txt_clip = (TextClip(text=year, 
                           font_size=70, 
                           color='white',
                           font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
                   .with_position(('left', 'bottom'))
                   .with_duration(1)
                   .with_start(i))
        text_clips.append(txt_clip)
    
    # Combine video and text
    final_clip = CompositeVideoClip([base_clip] + text_clips)
    
    # Save video in the main output folder with project name
    video_path = os.path.join(OUTPUT_FOLDER, f"{project_name}_timelapse.mp4")
    final_clip.write_videofile(video_path, fps=24)
    print(f"Timelapse video created: {video_path}")

def download_image(year, layer_type, project_folder):
    """
    Downloads an image for the specified year and layer type.
    """
    # Construct the URL with the appropriate parameters
    url = (
        f"{BASE_URL}?service=WMS&request=GetMap&layers={year}&styles=&format=image/jpeg"
        f"&transparent=false&version=1.1.1&width=512&height=512"
        f"&srs=EPSG:4326&bbox={BBOX}"
    )
    try:
        response = requests.get(url, headers=HEADERS, stream=True)
        if response.status_code == 200:
            filename = f"{year}_{layer_type}.jpg"
            filepath = os.path.join(project_folder, filename)
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
            print(f"Downloaded: {filename}")
        else:
            print(f"Failed to download {year} {layer_type}: {response.status_code}")
    except Exception as e:
        print(f"Error downloading {year} {layer_type}: {e}")

def reduce_watermark(input_path, output_path):
    """
    Reduces visibility of white text watermarks with black borders in the image.
    
    Args:
        input_path (str): Path to input image
        output_path (str): Path to save processed image
    """
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

def process_all_images(project_folder):
    """
    Process all images in the project folder to reduce watermark visibility.
    """
    # Create a subfolder for processed images
    processed_folder = os.path.join(project_folder, "processed")
    os.makedirs(processed_folder, exist_ok=True)
    
    # Process each image
    for year, _ in sorted(aerials, key=lambda x: x[0]):
        input_path = os.path.join(project_folder, f"{year}_A.jpg")
        if os.path.exists(input_path):
            output_path = os.path.join(processed_folder, f"{year}_A.jpg")
            print(f"Processing image for year {year}...")
            reduce_watermark(input_path, output_path)
    
    return processed_folder

def main():
    # Check for command line arguments
    if len(sys.argv) == 5:  # Program name + 4 arguments
        project_name = sys.argv[1]
        try:
            lat = float(sys.argv[2])
            lon = float(sys.argv[3])
            size = float(sys.argv[4])
        except ValueError:
            print("Invalid command line arguments. Format: python main.py project_name latitude longitude size")
            return
    else:
        # Fallback to interactive input
        project_name = input("Enter project name: ").strip()
        if not project_name:
            print("Project name is required")
            return
        
        try:
            lat = float(input("Enter center latitude (default 41.851150562): ") or CENTER_LAT)
            lon = float(input("Enter center longitude (default -87.662658691): ") or CENTER_LON)
            size = float(input("Enter box size in degrees (default 0.005): ") or 0.005)
        except ValueError:
            print("Invalid input. Please enter valid numbers.")
            return
    
    # Create project folder
    project_folder = os.path.join(OUTPUT_FOLDER, project_name)
    os.makedirs(project_folder, exist_ok=True)
    
    global BBOX
    BBOX = calculate_bbox(lat, lon, size)
    
    # Download images
    for year, layer_type in aerials:
        download_image(year, project_name, project_folder)
        time.sleep(0.1)
    
    # Process images to reduce watermark visibility
    print("\nReducing watermark visibility...")
    processed_folder = process_all_images(project_folder)
    
    # Create timelapse using processed images
    print("\nCreating timelapse video...")
    create_timelapse(project_folder, project_name)

if __name__ == "__main__":
    main()
