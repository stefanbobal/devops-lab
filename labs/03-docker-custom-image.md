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

## Today labs outputs:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ docker build -t fake-sap-api:v1 .
DEPRECATED: The legacy builder is deprecated and will be removed in a future release.
            Install the buildx component to build images with BuildKit:
            https://docs.docker.com/go/buildx/

Sending build context to Docker daemon  4.096kB
Step 1/7 : FROM python:3.13-slim
3.13-slim: Pulling from library/python
9b83eae799b8: Pulling fs layer
6310eb16bf42: Pulling fs layer
5bbcb35ea63e: Pulling fs layer
237e12970bdc: Pulling fs layer
9b83eae799b8: Download complete
237e12970bdc: Download complete
fad282f73736: Download complete
5bbcb35ea63e: Download complete
70a846509783: Download complete
6310eb16bf42: Download complete
6310eb16bf42: Pull complete
5bbcb35ea63e: Pull complete
237e12970bdc: Pull complete
9b83eae799b8: Pull complete
Digest: sha256:9d2e5553305c7c7b0097999bb17187c69b921ccd6bc9d40e4bb5ebe652c00285
Status: Downloaded newer image for python:3.13-slim
 ---> 9d2e5553305c
Step 2/7 : WORKDIR /app
 ---> Running in e570aa460f19
 ---> Removed intermediate container e570aa460f19
 ---> caec0456db08
Step 3/7 : COPY requirements.txt .
 ---> ed98536b2020
Step 4/7 : RUN pip install --no-cache-dir -r requirements.txt
 ---> Running in 3b298a6fba91
Collecting fastapi (from -r requirements.txt (line 1))
  Downloading fastapi-0.141.1-py3-none-any.whl.metadata (27 kB)
Collecting uvicorn (from -r requirements.txt (line 2))
  Downloading uvicorn-0.52.4-py3-none-any.whl.metadata (6.6 kB)
Collecting starlette>=0.46.0 (from fastapi->-r requirements.txt (line 1))
  Downloading starlette-1.6.0-py3-none-any.whl.metadata (6.4 kB)
Collecting pydantic>=2.9.0 (from fastapi->-r requirements.txt (line 1))
  Downloading pydantic-2.13.5-py3-none-any.whl.metadata (110 kB)
Collecting typing-extensions>=4.8.0 (from fastapi->-r requirements.txt (line 1))
  Downloading typing_extensions-4.16.0-py3-none-any.whl.metadata (3.3 kB)
Collecting typing-inspection>=0.4.2 (from fastapi->-r requirements.txt (line 1))
  Downloading typing_inspection-0.4.4-py3-none-any.whl.metadata (2.6 kB)
Collecting annotated-doc>=0.0.2 (from fastapi->-r requirements.txt (line 1))
  Downloading annotated_doc-0.0.5-py3-none-any.whl.metadata (6.5 kB)
Collecting click>=7.0 (from uvicorn->-r requirements.txt (line 2))
  Downloading click-8.5.0-py3-none-any.whl.metadata (2.6 kB)
Collecting h11>=0.8 (from uvicorn->-r requirements.txt (line 2))
  Downloading h11-0.16.0-py3-none-any.whl.metadata (8.3 kB)
Collecting annotated-types>=0.6.0 (from pydantic>=2.9.0->fastapi->-r requirements.txt (line 1))
  Downloading annotated_types-0.8.0-py3-none-any.whl.metadata (15 kB)
Collecting pydantic-core==2.46.5 (from pydantic>=2.9.0->fastapi->-r requirements.txt (line 1))
  Downloading pydantic_core-2.46.5-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl.metadata (6.6 kB)
Collecting anyio<5,>=3.6.2 (from starlette>=0.46.0->fastapi->-r requirements.txt (line 1))
  Downloading anyio-4.15.1-py3-none-any.whl.metadata (4.7 kB)
Collecting idna>=2.8 (from anyio<5,>=3.6.2->starlette>=0.46.0->fastapi->-r requirements.txt (line 1))
  Downloading idna-3.19-py3-none-any.whl.metadata (9.2 kB)
Downloading fastapi-0.141.1-py3-none-any.whl (131 kB)
Downloading uvicorn-0.52.4-py3-none-any.whl (79 kB)
Downloading annotated_doc-0.0.5-py3-none-any.whl (5.3 kB)
Downloading click-8.5.0-py3-none-any.whl (125 kB)
Downloading h11-0.16.0-py3-none-any.whl (37 kB)
Downloading pydantic-2.13.5-py3-none-any.whl (472 kB)
Downloading pydantic_core-2.46.5-cp313-cp313-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (2.1 MB)
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 2.1/2.1 MB 41.7 MB/s  0:00:00
Downloading annotated_types-0.8.0-py3-none-any.whl (13 kB)
Downloading starlette-1.6.0-py3-none-any.whl (75 kB)
Downloading anyio-4.15.1-py3-none-any.whl (132 kB)
Downloading idna-3.19-py3-none-any.whl (68 kB)
Downloading typing_extensions-4.16.0-py3-none-any.whl (45 kB)
Downloading typing_inspection-0.4.4-py3-none-any.whl (14 kB)
Installing collected packages: typing-extensions, idna, h11, click, annotated-types, annotated-doc, uvicorn, typing-inspection, pydantic-core, anyio, starlette, pydantic, fastapi

WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
Successfully installed annotated-doc-0.0.5 annotated-types-0.8.0 anyio-4.15.1 click-8.5.0 fastapi-0.141.1 h11-0.16.0 idna-3.19 pydantic-2.13.5 pydantic-core-2.46.5 starlette-1.6.0 typing-extensions-4.16.0 typing-inspection-0.4.4 uvicorn-0.52.4
 ---> Removed intermediate container 3b298a6fba91
 ---> eaf9c058004d
Step 5/7 : COPY app.py .
 ---> da49ba9552fb
Step 6/7 : EXPOSE 8000
 ---> Running in 44f1b51a858b
 ---> Removed intermediate container 44f1b51a858b
 ---> 120ac339c342
Step 7/7 : CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
 ---> Running in 8bfdca46a7d0
 ---> Removed intermediate container 8bfdca46a7d0
 ---> d26ba0cfcca8
Successfully built d26ba0cfcca8
Successfully tagged fake-sap-api:v1
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ 
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ 
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ 
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ ls -la
total 20
drwxrwxr-x 2 sapops sapops 4096 Sep  6 10:21 .
drwxrwxr-x 3 sapops sapops 4096 Sep  6 10:17 ..
-rw-rw-r-- 1 sapops sapops  208 Sep  6 10:21 Dockerfile
-rw-rw-r-- 1 sapops sapops  175 Sep  6 10:20 app.py
-rw-rw-r-- 1 sapops sapops   16 Sep  6 10:20 requirements.txt
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ docker ps
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ docker run -d \
  --name fake-sap-api \
  -p 8000:8000 \
  fake-sap-api:v1
bbf54b6ea7ebffa82031704fb63b3717e271f2ba937fd82e5d5457d8c14e380a
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ docker run -d \
  --name fake-sap-api \
  -p 8000:8000 \
  fake-sap-api:v1^C
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ curl http://localhost:8000/status
{"sid":"D50","application":"UP","database":"UP"}sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ 
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ 
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ 
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ docker ps
CONTAINER ID   IMAGE             COMMAND                  CREATED              STATUS              PORTS                                         NAMES
bbf54b6ea7eb   fake-sap-api:v1   "uvicorn app:app --h…"   About a minute ago   Up About a minute   0.0.0.0:8000->8000/tcp, [::]:8000->8000/tcp   fake-sap-api
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ docker logs fake-sap-api 
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     172.17.0.1:39468 - "GET /status HTTP/1.1" 200 OK
INFO:     172.17.0.1:44348 - "GET /status HTTP/1.1" 200 OK
INFO:     172.17.0.1:44348 - "GET /favicon.ico HTTP/1.1" 404 Not Found
INFO:     172.17.0.1:52246 - "GET / HTTP/1.1" 404 Not Found
INFO:     172.17.0.1:52246 - "GET /favicon.ico HTTP/1.1" 404 Not Found
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$
```


## At the end I build second version of docker image:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ docker build -t fake-sap-api:v2 .
DEPRECATED: The legacy builder is deprecated and will be removed in a future release.
            Install the buildx component to build images with BuildKit:
            https://docs.docker.com/go/buildx/

Sending build context to Docker daemon  4.096kB
Step 1/7 : FROM python:3.13-slim
 ---> 9d2e5553305c
Step 2/7 : WORKDIR /app
 ---> Using cache
 ---> caec0456db08
Step 3/7 : COPY requirements.txt .
 ---> Using cache
 ---> ed98536b2020
Step 4/7 : RUN pip install --no-cache-dir -r requirements.txt
 ---> Using cache
 ---> eaf9c058004d
Step 5/7 : COPY app.py .
 ---> 876144323be7
Step 6/7 : EXPOSE 8000
 ---> Running in ec60e788d28c
 ---> Removed intermediate container ec60e788d28c
 ---> 4bf16e93168c
Step 7/7 : CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
 ---> Running in cc23b2606707
 ---> Removed intermediate container cc23b2606707
 ---> 8d58c3b4acb5
Successfully built 8d58c3b4acb5
Successfully tagged fake-sap-api:v2
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ docker images
                                                                                                       i Info →   U  In Use
IMAGE              ID             DISK USAGE   CONTENT SIZE   EXTRA
fake-sap-api:v1    d26ba0cfcca8        223MB         54.6MB    U   
fake-sap-api:v2    8d58c3b4acb5        223MB         54.6MB        
python:3.13-slim   9d2e5553305c        189MB         48.2MB        
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api$ 
```