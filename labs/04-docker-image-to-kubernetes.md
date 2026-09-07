# Lab 04 - Deploy Custom Docker Image to Kubernetes

## Goal

Deploy a custom Docker image into Kubernetes and expose the application through a Kubernetes Service.

This lab connects the Docker concepts from the previous lab with the Kubernetes concepts from the earlier labs.

Topics covered:

- Importing a local Docker image into k3s
- Kubernetes Deployment
- Running a custom application in Pods
- Multiple replicas
- Kubernetes Service
- Testing the application through the Service
- Understanding the relationship between Docker and Kubernetes

---

## Application

The application used in this lab is the custom `fake-sap-api` created in the previous Docker lab.

Example endpoint:

```text
GET /status
```

Example response:

```json
{
  "sid": "DEV",
  "application": "UP",
  "database": "UP",
  "version": "2.0"
}
```

The application is packaged as the Docker image:

```text
fake-sap-api:v2
```

---

## Architecture

Before Kubernetes:

```text
app.py
  ↓
Dockerfile
  ↓
Docker image
  ↓
Docker container
  ↓
Port 8000
```

After deploying to Kubernetes:

```text
fake-sap-api:v2
        ↓
Kubernetes Deployment
        ↓
ReplicaSet
        ↓
Pods
        ↓
Containers
        ↓
Kubernetes Service
        ↓
HTTP request
```

With two replicas:

```text
Client
  ↓
fake-sap-api Service
  ↓
├── Pod 1
│   └── fake-sap-api:v2
│
└── Pod 2
    └── fake-sap-api:v2
```

---

## 1. Verify the Docker Image

Check that the Docker image exists:

```bash
docker images
```

Example:

```text
IMAGE              TAG
fake-sap-api       v2
```

---

## 2. Export the Docker Image

The image currently exists in the Docker image store.

k3s uses its own container runtime, so the image must first be exported.

Export the image:

```bash
docker save fake-sap-api:v2 -o fake-sap-api-v2.tar
```

Check the file:

```bash
ls -lh fake-sap-api-v2.tar
```

---

## 3. Import the Image into k3s

Import the Docker image into the k3s container runtime:

```bash
sudo k3s ctr images import fake-sap-api-v2.tar
```

Verify that k3s can see the image:

```bash
sudo k3s ctr images list | grep fake-sap-api
```

The image should now be available to Kubernetes.

---

## 4. Create the Kubernetes Deployment

Create the directory for Kubernetes manifests:

```bash
mkdir -p projects/fake-sap-api/k8s
```

Create:

```text
projects/fake-sap-api/k8s/deployment.yaml
```

Example Deployment:

```yaml
apiVersion: apps/v1
kind: Deployment

metadata:
  name: fake-sap-api

spec:
  replicas: 2

  selector:
    matchLabels:
      app: fake-sap-api

  template:
    metadata:
      labels:
        app: fake-sap-api

    spec:
      containers:
        - name: fake-sap-api
          image: fake-sap-api:v2
          imagePullPolicy: Never

          ports:
            - containerPort: 8000
```

---

## 5. Deployment Explanation

### replicas

```yaml
replicas: 2
```

Kubernetes should maintain two running Pods.

---

### selector

```yaml
selector:
  matchLabels:
    app: fake-sap-api
```

The Deployment uses this label to identify the Pods it manages.

---

### image

```yaml
image: fake-sap-api:v2
```

This is the custom image created in the Docker lab.

---

### imagePullPolicy

```yaml
imagePullPolicy: Never
```

This tells Kubernetes not to download the image from an external registry.

The image already exists locally in the k3s container runtime.

---

### containerPort

```yaml
containerPort: 8000
```

The Python application listens on port `8000` inside the container.

---

## 6. Apply the Deployment

Deploy the application:

```bash
sudo kubectl apply -f projects/fake-sap-api/k8s/deployment.yaml
```

Check the Deployment:

```bash
sudo kubectl get deployments
```

Check the Pods:

```bash
sudo kubectl get pods
```

Expected result:

```text
NAME                            READY   STATUS    RESTARTS
fake-sap-api-xxxxxxxxxx-aaaaa   1/1     Running   0
fake-sap-api-xxxxxxxxxx-bbbbb   1/1     Running   0
```

---

## 7. Inspect Pod Placement

Display more detailed information:

```bash
sudo kubectl get pods -o wide
```

This shows:

- Pod names
- Pod IP addresses
- Node where the Pod is running
- Pod status

---

## 8. Check Application Logs

Display logs for one Pod:

```bash
sudo kubectl logs <pod-name>
```

Example:

```bash
sudo kubectl logs fake-sap-api-xxxxxxxxxx-aaaaa
```

The logs should show the Uvicorn application starting.

---

## 9. Create a Kubernetes Service

Create a Service for the Deployment:

```bash
sudo kubectl expose deployment fake-sap-api \
  --port=8000 \
  --target-port=8000 \
  --type=ClusterIP
```

Check the Service:

```bash
sudo kubectl get services
```

Example:

```text
NAME           TYPE        CLUSTER-IP      PORT(S)
fake-sap-api   ClusterIP   10.43.x.x       8000/TCP
```

---

## 10. Test the Application

Send an HTTP request to the Service:

```bash
curl http://<SERVICE-IP>:8000/status
```

Example:

```bash
curl http://10.43.x.x:8000/status
```

Expected result:

```json
{
  "sid": "DEV",
  "application": "UP",
  "database": "UP",
  "version": "2.0"
}
```

This confirms the complete flow:

```text
curl
  ↓
Kubernetes Service
  ↓
fake-sap-api Pod
  ↓
Docker container
  ↓
FastAPI application
```

---

## 11. Test High Availability

Check the Pods:

```bash
sudo kubectl get pods
```

Delete one Pod:

```bash
sudo kubectl delete pod <pod-name>
```

Check again:

```bash
sudo kubectl get pods
```

The Deployment automatically creates a replacement Pod.

The Service continues to provide the same stable endpoint.

---

## 12. Docker vs Kubernetes Responsibility

Docker is responsible for packaging the application:

```text
Source code
   ↓
Dockerfile
   ↓
Docker image
```

Kubernetes is responsible for running and managing the application:

```text
Docker image
   ↓
Deployment
   ↓
Pods
   ↓
Service
```

Simplified:

```text
Docker = package the application

Kubernetes = operate the application
```

---

## 13. Useful Commands

Check images available in k3s:

```bash
sudo k3s ctr images list
```

Check Deployments:

```bash
sudo kubectl get deployments
```

Check Pods:

```bash
sudo kubectl get pods
```

Check detailed Pod information:

```bash
sudo kubectl get pods -o wide
```

Check Services:

```bash
sudo kubectl get services
```

Show Pod logs:

```bash
sudo kubectl logs <pod-name>
```

Describe a Pod:

```bash
sudo kubectl describe pod <pod-name>
```

Describe the Deployment:

```bash
sudo kubectl describe deployment fake-sap-api
```

Delete a Pod:

```bash
sudo kubectl delete pod <pod-name>
```

---

## Key Takeaways

- Docker images can be used as Kubernetes workloads.
- k3s uses a container runtime separate from the Docker image store.
- A Docker image can be imported into the k3s runtime.
- A Kubernetes Deployment manages application Pods.
- Multiple replicas improve availability.
- A Service provides a stable network endpoint.
- Kubernetes can replace failed Pods automatically.
- Docker packages applications.
- Kubernetes orchestrates and operates applications.

---

## Next Step

The next step will be to externalize application configuration.

Instead of hardcoding values such as:

```json
{
  "sid": "DEV",
  "application": "UP",
  "database": "UP"
}
```

the application will use:

```text
ConfigMap
Secret
```

This allows configuration to change without rebuilding the Docker image.


## Actions and steps done on todays lab

saved docker image into local tar:

```bash
docker save fake-sap-api:v2 -o fake-sap-api-v2.tar
```


imported local docker image into kubernetes

```bash
sudo k3s ctr images import fake-sap-api-v2.tar
```

List of kubernetes images:

```bash
sudo k3s ctr images list | grep fake-sap-api
docker.io/library/fake-sap-api:v2                                                                                  application/vnd.oci.image.manifest.v1+json                sha256:fd212d07b1ede9de7a6b44463afdb4a6abf265af80eeefa0bfe3bff5963282f4 52.0 MiB  linux/amd64                                                                                            io.cri-containerd.image=managed 
```

Created kubernetes deployment manifest for kubernetes:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ cat deployment.yaml 
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fake-sap-api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: fake-sap-api
  template:
    metadata:
      labels:
        app: fake-sap-api
    spec:
      containers:
        - name: fake-sap-api
          image: fake-sap-api:v2
          imagePullPolicy: Never
          ports:
            - containerPort: 8000
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ 
```

Applied the Deployment manifest to the Kubernetes cluster:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl apply -f deployment.yaml
deployment.apps/fake-sap-api created
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$



apops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl get deployments
NAME           READY   UP-TO-DATE   AVAILABLE   AGE
fake-sap-api   2/2     2            2           18s
nginx          3/3     3            3           42h
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$
```

deleted old deployment from previous lab:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl delete deployment nginx
deployment.apps "nginx" deleted from default namespace
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl delete service nginx
service "nginx" deleted from default namespace
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ 
```


check all details of kubernetes cluster:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl get all
NAME                                READY   STATUS    RESTARTS   AGE
pod/fake-sap-api-59cffcfbdf-4rlv4   1/1     Running   0          90s
pod/fake-sap-api-59cffcfbdf-ngrd7   1/1     Running   0          90s

NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
service/kubernetes   ClusterIP   10.43.0.1    <none>        443/TCP   42h

NAME                           READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/fake-sap-api   2/2     2            2           92s

NAME                                      DESIRED   CURRENT   READY   AGE
replicaset.apps/fake-sap-api-59cffcfbdf   2         2         2       92s
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$
```

Create (expose) kubernetes service for deployment fake-sap-api:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl expose deployment fake-sap-api \
  --port=8000 \
  --target-port=8000 \
  --type=ClusterIP
service/fake-sap-api exposed
```

We can see that service is exposed and endpoint available:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl get services
NAME           TYPE        CLUSTER-IP    EXTERNAL-IP   PORT(S)    AGE
fake-sap-api   ClusterIP   10.43.9.211   <none>        8000/TCP   6s
kubernetes     ClusterIP   10.43.0.1     <none>        443/TCP    42h
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ curl http://10.43.9.211:8000/status
{"sid":"D50","application":"UP","database":"DOWN","version":"2.0"}sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ 
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ 


sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl get endpoints fake-sap-api
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME           ENDPOINTS                         AGE
fake-sap-api   10.42.0.38:8000,10.42.0.39:8000   62s
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl get endpointslices
NAME                 ADDRESSTYPE   PORTS   ENDPOINTS               AGE
fake-sap-api-jrbnp   IPv4          8000    10.42.0.39,10.42.0.38   100s
kubernetes           IPv4          6443    192.168.178.110         42h
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ 
```

We configured deployment to have exactly 2 pods (configured in deployment.yaml as replicas: 2), so now we will test if we delete one pod it should recreate it automatically:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl get pods
NAME                            READY   STATUS    RESTARTS   AGE
fake-sap-api-59cffcfbdf-4rlv4   1/1     Running   0          5m35s
fake-sap-api-59cffcfbdf-ngrd7   1/1     Running   0          5m35s
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$
```

Deleted one of the pods:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl delete pod fake-sap-api-59cffcfbdf-ngrd7
pod "fake-sap-api-59cffcfbdf-ngrd7" deleted from default namespace
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ 
```


And now we can see that new pod is started with new name:

```bash
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$ sudo kubectl get pods
NAME                            READY   STATUS    RESTARTS   AGE
fake-sap-api-59cffcfbdf-4rlv4   1/1     Running   0          6m7s
fake-sap-api-59cffcfbdf-qgq4x   1/1     Running   0          11s
sapops@k8s-lab:~/devops-lab/projects/fake-sap-api/k8s$
```

