# Lab 03 - Docker Basics and Custom Image

## Goal

Learn the basic Docker workflow by creating a small custom application, packaging it into a Docker image and running it as a container.

The application used in this lab simulates a very small SAP system status API.

Topics covered:

- Docker image
- Container
- Dockerfile
- Image build
- Port mapping
- Container lifecycle
- Logs
- Interactive shell
- Application packaging

---

## Project Structure

The application files are stored separately from the lab documentation.

```text
devops-lab/
├── labs/
│   └── 03-docker-custom-image.md
│
└── projects/
    └── fake-sap-api/
        ├── app.py
        ├── requirements.txt
        └── Dockerfile
```

---

## 1. Application Concept

The demo application is a small Python API that simulates the status of an SAP system.

Example endpoint:

```text
GET /status
```

Expected response:

```json
{
  "sid": "DEV",
  "application": "UP",
  "database": "UP"
}
```

The purpose of this application is not to simulate SAP in detail.

It is used as a simple workload for learning Docker and later Kubernetes.

---

## 2. Docker Workflow

The basic Docker workflow used in this lab is:

```text
Application source code
        ↓
Dockerfile
        ↓
docker build
        ↓
Docker image
        ↓
docker run
        ↓
Running container
```

---

## 3. Create the Application

The application will be created in:

```text
projects/fake-sap-api/
```

The application will use Python and FastAPI.

Application file:

```text
app.py
```

Dependencies:

```text
requirements.txt
```

Container definition:

```text
Dockerfile
```

---

## 4. Build the Docker Image

Build the image from the Dockerfile:

```bash
docker build -t fake-sap-api:v1 .
```

Check available images:

```bash
docker images
```

Expected result:

```text
REPOSITORY      TAG    IMAGE ID       CREATED        SIZE
fake-sap-api    v1     <image-id>     <time>         <size>
```

---

## 5. Run the Container

Start the application container:

```bash
docker run -d \
  --name fake-sap-api \
  -p 8000:8000 \
  fake-sap-api:v1
```

Explanation:

```text
-d
```

Runs the container in detached mode.

```text
--name fake-sap-api
```

Assigns a readable name to the container.

```text
-p 8000:8000
```

Maps port 8000 on the Linux host to port 8000 inside the container.

---

## 6. Check Running Containers

Display running containers:

```bash
docker ps
```

Example:

```text
CONTAINER ID   IMAGE             STATUS        PORTS
xxxxxxxxxxxx   fake-sap-api:v1   Up ...        0.0.0.0:8000->8000/tcp
```

---

## 7. Test the Application

Send an HTTP request to the API:

```bash
curl http://localhost:8000/status
```

Expected response:

```json
{
  "sid": "DEV",
  "application": "UP",
  "database": "UP"
}
```

This confirms that:

```text
Linux host
   ↓
Port 8000
   ↓
Docker container
   ↓
Python application
```

is working correctly.

---

## 8. Check Container Logs

Display the application logs:

```bash
docker logs fake-sap-api
```

Follow logs continuously:

```bash
docker logs -f fake-sap-api
```

---

## 9. Enter the Running Container

Open a shell inside the container:

```bash
docker exec -it fake-sap-api sh
```

This allows inspection of the filesystem and running environment inside the container.

Exit the container shell:

```bash
exit
```

---

## 10. Stop and Remove the Container

Stop the container:

```bash
docker stop fake-sap-api
```

Remove the container:

```bash
docker rm fake-sap-api
```

The Docker image still remains available.

Check images:

```bash
docker images
```

---

## Image vs Container

An image is a packaged application template.

A container is a running instance of that image.

```text
fake-sap-api:v1 image
        ↓
docker run
        ↓
fake-sap-api container
```

Multiple containers can be created from the same image.

Example:

```text
fake-sap-api:v1 image
        ↓
├── container 1
├── container 2
└── container 3
```

---

## Port Mapping

The application listens on port:

```text
8000
```

inside the container.

Docker maps the Linux host port to the container port:

```text
Linux VM:8000
      ↓
Container:8000
```

The mapping is created with:

```bash
-p 8000:8000
```

---

## Useful Commands

List images:

```bash
docker images
```

List running containers:

```bash
docker ps
```

List all containers:

```bash
docker ps -a
```

Build image:

```bash
docker build -t fake-sap-api:v1 .
```

Run container:

```bash
docker run -d --name fake-sap-api -p 8000:8000 fake-sap-api:v1
```

View logs:

```bash
docker logs fake-sap-api
```

Open shell in container:

```bash
docker exec -it fake-sap-api sh
```

Stop container:

```bash
docker stop fake-sap-api
```

Remove container:

```bash
docker rm fake-sap-api
```

Remove image:

```bash
docker rmi fake-sap-api:v1
```

---

## Key Takeaways

- A Docker image packages an application and its dependencies.
- A container is a running instance of an image.
- A Dockerfile defines how an image is built.
- Docker can expose application ports to the host.
- The same Docker image can be used to create multiple containers.
- Containers are disposable, while images are reusable.
- Application logs can be inspected with `docker logs`.
- Containers can be inspected interactively with `docker exec`.
- This image can later be deployed into Kubernetes without changing the application itself.

---

## Next Step

The next step will be to deploy the same `fake-sap-api` Docker image into Kubernetes.

The application will move from:

```text
Docker
  ↓
Container
```

to:

```text
Kubernetes
  ↓
Deployment
  ↓
Pod
  ↓
Container
  ↓
fake-sap-api image
```

This will connect the Docker concepts from this lab with the Kubernetes concepts from the previous labs.