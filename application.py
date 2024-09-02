# """
# please make a program that does the following in order.
# 1. create a python flask server that receives a json object with one frame from a thermal camera. 
# THe format of the frame is a 24x32 matrix of integers representing the temperature in Celsius.
# The format of the json object is {"serial_number": "1234567890", "frame":[24x32 matrix]}
# 2. put the json of the frame received from camera in a file in s3 in a directory named after the serial number of the camera
# 3. we accumulate the json objects in a file called frame.json. When there are 6 json objects copy all of them in memory and empty the frame.json
# 4. create a collage of the 6 frames and put it in s3 in a file called pictures.jpg
# 5. ask openai to analyze the collage and return a json object with the following keys:
# {"presence of figures that look like a homo sapien or their body parts in the series of the images": <bool>,
# "description of what you see (arms, legs, face, torso, etc.)": <str>,
# "summary of above key points in dictionary format with the following key: human_present": {}
# }
# 6. check for a fire(spots above 60C) in the 6 json objects
# 7. take the human present key answer and the fire present key answer accumulate it in the smae directory but in another file called analysis.txt
# 8. when theh number of entries in the analysis.txt reaches 27, delete oldest 7 of them
# 9. read all entries in analysis.txt and if all entries have no human and 90% entries have fire, then call a method called handle emergency
# """
# from __future__ import annotations
from flask import Flask, request, jsonify
import boto3
import json
import os
import re
import io
import json
import matplotlib.pyplot as plt
import numpy as np
import base64
from openai import OpenAI

# Initialize S3 client
s3 = boto3.client('s3')
bucket_name = 'hello-response'

def create_image_collage_from_file(frames_data, pictures_file):
    # Reshape the data to 6 frames of 24x32 pixels and create a single image collage
    image_data = np.array(frames_data[-6:]).reshape(6, 24, 32)
    image_data = np.clip(image_data, None, 35)  # Clip values to a maximum of 35 WHY 35 BROOOOOOOOOO???
    fig, axs = plt.subplots(1, 6, figsize=(15, 5))
    for i, frame in enumerate(image_data):
        axs[i].imshow(frame, cmap='inferno')
        axs[i].axis('off')
    plt.subplots_adjust(wspace=0.1, hspace=0)
    
    # Save the figure to a PNG file in memory
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    
    # Upload the image to S3
    s3.put_object(Bucket=bucket_name, Key=pictures_file, Body=buf, ContentType='image/jpeg')
    
    # Close the plot to free up memory
    plt.close(fig)
    
    return {"status": "done", "image": pictures_file}





# # # EB looks for an 'application' callable by default.
# # application = Flask(__name__)

# # # add a rule to process commands.
# # @application.route('/x12', methods=['POST'])
# # def command():
# #     data = request.get_json() # Expected format: {"frames": [....]}
# #     return jsonify(process_data(data))

# client = OpenAI()
# # # Path to the JSON file containing all images
# # file_path = 'party_images1.json'

# # def read_new_image():
# #     """
# #     Generator function to yield one image data at a time from the file.
# #     """
# #     with open(file_path, 'r') as file:
# #         for line in file:
# #             yield json.loads(line)

# # def encode_image(image_path):
# #     """
# #     Encodes an image to a base64 string.
# #     """
# #     with open(image_path, "rb") as image_file:
# #         return base64.b64encode(image_file.read()).decode("utf-8")

def analyze_image(image_key):
    """
    Fetches the image from S3 and sends it to the API for analysis. The response includes information about the scene with a focus on humans and a boolean indicating the presence of humans.
    """
    import logging
    logging.info("analyze_image: %s", image_key)
    
    response = s3.get_object(Bucket=bucket_name, Key=image_key)
    image_data = response['Body'].read()
    encoded_string = base64.b64encode(image_data).decode("utf-8")

    user_prompt = """
    Do the following analysis for the image and return the following JSON:
    {
        "presence of figures that look like a homo sapien or their body parts in the series of the images": <bool>,
        "description of what you see (arms, legs, face, torso, etc.)": <str>,
        "description of the overall temperature range and if there is any chance of a fire": <str>,
        "human_present": <bool>
    }
    """
    response = OpenAI().chat.completions.create(
        model="gpt-4o",
        messages=[
            {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_prompt,
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{encoded_string}",
                    },
                },
            ],
            }
        ],
        max_tokens=300,
    )

    # Extracting and formatting the response
    full_response_content = response.choices[0].message.content
    logging.info("full_response_content: %s", full_response_content)
    try:
        # Attempt to find JSON enclosed in triple backticks
        analysis_result_match = re.search(r"```json(.+?)```", full_response_content, re.DOTALL)
        if not analysis_result_match:
            logging.info("analysis_items: WITHIN ```json")

            # If not found, attempt to find JSON enclosed in any triple backticks
            analysis_result_match = re.search(r"```(.+?)```", full_response_content, re.DOTALL)
        if not analysis_result_match:
            logging.info("analysis_items: WITHIN ```")

            # If not found, attempt to find JSON without backticks
            analysis_result_match = re.search(r"{.+}", full_response_content, re.DOTALL)
        analysis_result = analysis_result_match.group(1) if analysis_result_match else "{}"
        logging.info("analysis_result: %s", analysis_result)

        analysis_items = json.loads(analysis_result)
        logging.info("analysis_items: %s", analysis_items)
        return analysis_items
    except Exception as e:
        logging.error("An error occurred while processing analysis_items: %s", e)
        return {}

# # def test_create_image_collage_from_file():
# #     # Assuming frame.json exists and is correctly formatted
# #     result = create_image_collage_from_file()
# #     # Analyze the image
# #     analysis_result = analyze_image('pictures.jpg')
# #     # Print results
# #     print("Image Collage Creation Result:", result)
# #     print("Image Analysis Result:", analysis_result)

# # test_create_image_collage_from_file()



application = Flask(__name__)


@application.route('/x12', methods=['POST'])
def upload_frame():
    import logging
    data = request.get_json()
    logging.basicConfig(level=logging.INFO)
    logging.info("upload_frame: %s", data)
    serial_number = data.get('serial_number', 'unknown')
    frame = data.get('frame')
    frames_file = f'{serial_number}/frames.json'
    pictures_file = f'{serial_number}/pictures.jpg'
    analysis_file = f'{serial_number}/analysis.txt'
    
    # Accumulate frames in frame.json
    import logging
    frames_data = []
    try:
        response = s3.get_object(Bucket=bucket_name, Key=frames_file)
        frames_data = json.loads(response['Body'].read().decode('utf-8'))
    except s3.exceptions.NoSuchKey:
        frames_data = []
    

    logging.basicConfig(level=logging.INFO)
    logging.info("frames_data: %s", frames_data)
    frames_data.append(frame)

    if len(frames_data) >= 6:
        # Create collage and analyze
        result = create_image_collage_from_file(frames_data=frames_data, pictures_file=pictures_file)
        if result["status"] == "error":
            return jsonify(result), 500
        analysis_result = analyze_image(pictures_file)
        
        # Check for fire
        fire_present = any(any(temp > 45 for temp in frame) for frame in frames_data)
        
        # Accumulate analysis results
        analysis_entry = {
            "human_present": analysis_result['human_present'],
            "fire_present": fire_present
        }
        try:
            analysis_response = s3.get_object(Bucket=bucket_name, Key=analysis_file)
            analysis_data = json.loads(analysis_response['Body'].read().decode('utf-8'))
        except s3.exceptions.NoSuchKey:
            analysis_data = []
        analysis_data.append(analysis_entry)
        
        if len(analysis_data) > 5:
            analysis_data = analysis_data[-5:]
        
        s3.put_object(Bucket=bucket_name, Key=analysis_file, Body=json.dumps(analysis_data))
        
        # Check for emergency
        if not any(entry['human_present'] for entry in analysis_data) and sum(entry['fire_present'] for entry in analysis_data) >= 0.8 * len(analysis_data):
            handle_emergency(analysis_data)
        # Empty frames.json
        frames_data = frames_data[-5:]
    
    s3.put_object(Bucket=bucket_name, Key=frames_file, Body=json.dumps(frames_data))
    
    return jsonify({"success": True}), 200

from twilio import rest

Client = rest.Client

import os

def handle_emergency(analysis_data):
    # Twilio credentials
    '''
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    client = Client(account_sid, auth_token)
    
    # Read analysis.txt
    with open('analysis.txt', 'r') as file:
        analysis_data = json.load(file)
    
    # Check if all entries show {"human_present": false, "fire_present": true}
    if all(entry['human_present'] == False and entry['fire_present'] == True for entry in analysis_data):
        message = client.messages.create(
            body="Fire detected. There is an unattende
            d fire in your kitchen.",
            from_=os.getenv('TWILIO_FROM_NUMBER'),  # Your Twilio number
            to=os.getenv('TWILIO_TO_NUMBER')        # Your phone number
        )
        print(f"Emergency message sent: {message.sid}")
    '''
    
    import os
    import requests
    import logging

    # Read environment variables
    api_key = os.getenv("ONESIGNAL_API_KEY")
    app_id = os.getenv("ONESIGNAL_APP_ID")

    url = "https://api.onesignal.com/notifications"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {api_key}"
    }
    data = {
        "app_id": app_id,
        "contents": {
            "en": "Fire detected. There has been an unattended fire in your kitchen for time to be known. maybe reeduce because long itme yk.",
            "es": "Hola Mundo",
            "fr": "Bonjour le monde",
            "zh-Hans": "\u4f60\u597d\u4e16\u754c"
        },
        "target_channel": "push",
        "included_segments": ["Total Subscriptions"]
    }
    logging.info("data: %s", data)

    try:
        response = requests.post(url, headers=headers, json=data)
        logging.info("Response status code: %s", response.status_code)
        logging.info("Response JSON: %s", response.json())
    except Exception as e:
        logging.error("Error occurred: %s", e)

   #print(message.sid)

if __name__ == '__main__':
    application.run(debug=True)


