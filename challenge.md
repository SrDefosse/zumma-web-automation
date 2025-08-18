Technical Challenge: Web Automation Backend
Your task is to build a REST API that automates data extraction from websites using
Playwright.
Main Objective
Develop a REST API using Python that can automate data extraction from different
websites. The core of the application will be a web automation script powered by
Playwright.
The challenge requires you to:
1. Extract Data: Automate the process of navigating and extracting specific data
from a given website.
2. Normalize & Store: Take the extracted data, normalize its format, and store it in a
PostgreSQL database.
3. Provide Results: The API should provide the extracted and normalized data in
the response of a task status request.
Required Technologies
You must use the following technologies for this challenge:
● Backend Language: Python
● Web Automation: Playwright
● Database: PostgreSQL
● Containerization: Docker

Application Requirements
Your application must meet the following requirements:
1. Data Model & Normalization
● Define a database schema that can store the extracted data from different
websites in a normalized format.
● Implement data validation to ensure the integrity of the data being stored.
● Data Structure: The extracted product information should be represented in a
consistent JSON format. The GET /tasks/{job_id} endpoint, when a task is
completed, must return a response body structured as follows:

{
 "status": "completed",
 "data": [
 {
 "name": "string",
 "price": "string",
 "description": "string",
 "image_url": "string"
 },
 ...
 ]
}

The image_url must be a URL from your backend that serves the downloaded image

2. REST API Endpoints
● POST /tasks: This endpoint will initiate a new automation task.
    ○ It should accept a JSON body containing a unique identifier (task_id) that
    represents the specific website to be automated.
    ○ It can also accept an optional lookup_key parameter to search for a specific
    product on the website.
    ○ The API should respond with a 202 Accepted status and a unique job_id for
the newly created task.
● GET /tasks/{job_id}: This endpoint will provide information about a specific
automation task.
    ○ It should return the current status of the task (pending, in_progress,
    completed, failed).
    ○ If the task is completed, the response should include the extracted and
    normalized data from the database.
    ○ If the task has failed, the response should include an error message with the
    following data structure:

    {
    "status": "failed",
    "error_message": "string"
    }

3. Containerization
● The entire application, including the Python backend and the PostgreSQL
database, must be containerized using Docker.
● Provide a docker-compose.yml file that allows for the easy setup and execution of
the entire service with a single command.


Websites to Automate
Your solution should demonstrate its versatility by supporting at least two different
automation tasks:
Task 1: Saucedemo Product Scraping
● Website: https://www.saucedemo.com/
● Task Objective:
1. Log into the website using the provided credentials (standard_user/secret_sauce).
2. Navigate to the products page.
3. For each product, capture the following data:
○ Name
○ Price
○ Description
○ Image URL: The image must be downloaded and stored locally. The URL
provided in the API response must be a URL from your backend service that
serves the downloaded image.
4. Store this data in the database.
5. The GET endpoint response for this task should be the list of product data.


Task 2: Practice Software Testing Product Scraping
● Website: https://practicesoftwaretesting.com/
● Task Objective:
1. Navigate to the products page.
2. For each product, capture the following data:
■ Name
■ Price
■ Description
■ Image URL: The image must be downloaded and stored locally. The URL
provided in the API response must be a URL from your backend service
that serves the downloaded image.
3. Store this data in the database.
4. The GET endpoint response for this task should be the list of product data.


Nice to Haves
These are not mandatory requirements, but implementing them would demonstrate a
deeper understanding of building robust and scalable applications.
● Asynchronous Processing: Use an asynchronous approach for web automation
with Playwright and database interactions.
● Testing: Implement unit and integration tests using a framework like pytest to
ensure code reliability and catch regressions.
● Task Queue: Use a task queue (e.g., Celery) to manage the background scraping
jobs, separating the API request from the long-running automation process.
● Structured Logging: Implement structured logging to provide clear, consistent,
and machine-readable logs.
● Configuration Management: Utilize a proper configuration management tool or
pattern to handle database credentials and other settings.
● Python Package Manager: Utilize one of the python packages besides pip to
install and manage dependencies.
● Command Management: Define a way to define and reuse common commands
to run and test the application.
Deliverables
● A public GitHub repository containing the complete, runnable code solution.
● A comprehensive README.md file that includes:
○ An overview of what the project does.
○ A list and description of all available API endpoints.
○ Detailed instructions on how to set up the project, including configuration
requirements.
○ Instructions on how to run the project locally using Docker Compose.