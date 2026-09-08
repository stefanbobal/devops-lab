# Lab 05 - ConfigMaps & Secrets

## Goal

Externalize application configuration from the Docker image and manage configuration through Kubernetes.

This lab demonstrates the difference between:

- application code
- non-sensitive configuration
- sensitive configuration

Topics covered:

- Environment variables
- ConfigMap
- Secret
- Injecting configuration into Pods
- Updating configuration without rebuilding the image
- Understanding why Secrets should not be stored in plaintext in Git

---

## Architecture

Before this lab, configuration was hardcoded directly in the application:

```text
app.py
  ↓
Docker image
  ↓
Kubernetes Deployment
```

After this lab:

```text
Docker image
  ↓
Kubernetes Deployment
  ↓
Pod
  ├── ConfigMap
  └── Secret
```

The Docker image contains only the application.

The runtime configuration is supplied by Kubernetes.

---

## 1. Update the Application

Update `app.py` so that configuration is read from environment variables.

Example:

```python
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/status")
def status():
    return {
        "sid": os.getenv("SAP_SID", "UNKNOWN"),
        "application": os.getenv("APP_STATUS", "UNKNOWN"),
        "database": os.getenv("DB_STATUS", "UNKNOWN"),
        "version": "3.0",
        "user": os.getenv("SAP_USER", "UNKNOWN")
    }
```

Example:

```python
os.getenv("SAP_SID", "UNKNOWN")
```

means:

```text
Read the SAP_SID environment variable.

If the variable does not exist, return UNKNOWN.
```

---

## 2. Build a New Docker Image

Build version `v3` of the application:

```bash
docker build -t stefanbobal/fake-sap-api:v3 .
```

Push the image to Docker Hub:

```bash
docker push stefanbobal/fake-sap-api:v3
```

The image now contains the application logic, but runtime configuration will be supplied separately by Kubernetes.

---

## 3. Create a ConfigMap

Create:

```text
projects/fake-sap-api/k8s/configmap.yaml
```

Example:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fake-sap-api-config

data:
  SAP_SID: "D50"
  APP_STATUS: "UP"
  DB_STATUS: "DOWN"
```

The ConfigMap contains non-sensitive configuration.

Examples of values suitable for a ConfigMap:

```text
SAP SID
application status
database status
API URL
feature flags
log level
```

---

## 4. Create a Secret

Create:

```text
projects/fake-sap-api/k8s/secret.yaml
```

Example:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: fake-sap-api-secret

type: Opaque

stringData:
  SAP_USER: "monitor"
  SAP_PASSWORD: "supersecret"
```

The Secret contains sensitive configuration.

Examples:

```text
passwords
API tokens
credentials
private keys
```

Important:

```text
stringData
```

is stored as plaintext in the YAML file.

Do not commit this file into a public Git repository.

---

## Kubernetes Secret Security

Kubernetes Secrets should not be confused with encryption.

For example:

```yaml
data:
  SAP_PASSWORD: c3VwZXJzZWNyZXQ=
```

is only Base64 encoded.

Base64 is not encryption.

It can easily be decoded.

Because of this, plain Kubernetes Secret manifests should normally not be stored directly in Git.

A later lab will use:

```text
kubeseal
Sealed Secrets
```

to encrypt secrets before storing them in Git.

---

## 5. Update the Deployment

Update the application image in `deployment.yaml`:

```yaml
image: stefanbobal/fake-sap-api:v3
```

Add configuration references to the container:

```yaml
envFrom:
  - configMapRef:
      name: fake-sap-api-config

  - secretRef:
      name: fake-sap-api-secret
```

Example container configuration:

```yaml
containers:
  - name: fake-sap-api
    image: stefanbobal/fake-sap-api:v3

    ports:
      - containerPort: 8000

    envFrom:
      - configMapRef:
          name: fake-sap-api-config

      - secretRef:
          name: fake-sap-api-secret
```

---

## 6. How envFrom Works

The Deployment references:

```text
fake-sap-api-config
```

and:

```text
fake-sap-api-secret
```

Kubernetes injects the values into the Pod as environment variables.

Example:

```text
ConfigMap
  ↓
SAP_SID=D50
APP_STATUS=UP
DB_STATUS=DOWN

Secret
  ↓
SAP_USER=monitor
SAP_PASSWORD=supersecret
```

Inside the container:

```text
SAP_SID
APP_STATUS
DB_STATUS
SAP_USER
SAP_PASSWORD
```

are available as normal environment variables.

The Python application reads them using:

```python
os.getenv(...)
```

---

## 7. Apply the ConfigMap

Apply the ConfigMap:

```bash
sudo kubectl apply -f configmap.yaml
```

Expected output:

```text
configmap/fake-sap-api-config created
```

Check the ConfigMap:

```bash
sudo kubectl get configmaps
```

Inspect it:

```bash
sudo kubectl describe configmap fake-sap-api-config
```

---

## 8. Apply the Secret

Apply the Secret:

```bash
sudo kubectl apply -f secret.yaml
```

Expected output:

```text
secret/fake-sap-api-secret created
```

Check Secrets:

```bash
sudo kubectl get secrets
```

Inspect the Secret metadata:

```bash
sudo kubectl describe secret fake-sap-api-secret
```

Kubernetes does not display the plaintext Secret values in `describe`.

---

## 9. Apply the Updated Deployment

Apply the Deployment:

```bash
sudo kubectl apply -f deployment.yaml
```

Check rollout status:

```bash
sudo kubectl rollout status deployment/fake-sap-api
```

Expected result:

```text
deployment "fake-sap-api" successfully rolled out
```

Check Pods:

```bash
sudo kubectl get pods
```

---

## 10. Test the Application

Check the Service:

```bash
sudo kubectl get services
```

Send an HTTP request:

```bash
curl http://<SERVICE-IP>:8000/status
```

Example:

```bash
curl http://10.43.9.211:8000/status
```

Expected response:

```json
{
  "sid": "D50",
  "application": "UP",
  "database": "DOWN",
  "version": "3.0",
  "user": "monitor"
}
```

The response now uses configuration supplied by Kubernetes.

---

## 11. Inspect Environment Variables Inside the Pod

List Pods:

```bash
sudo kubectl get pods
```

Open a shell inside one Pod:

```bash
sudo kubectl exec -it <pod-name> -- sh
```

Check environment variables:

```bash
env | grep SAP
```

Example:

```text
SAP_SID=D50
SAP_USER=monitor
SAP_PASSWORD=supersecret
```

Check application status variables:

```bash
env | grep STATUS
```

Exit the Pod:

```bash
exit
```

---

## 12. ConfigMap vs Secret

Use a ConfigMap for non-sensitive configuration:

```text
SID
API URL
log level
feature flags
application mode
```

Use a Secret for sensitive information:

```text
password
token
credentials
private key
```

Conceptually:

```text
ConfigMap
   ↓
normal configuration

Secret
   ↓
sensitive configuration
```

---

## 13. Why Configuration Should Not Be Inside the Image

Without external configuration:

```text
DEV image
QAS image
PRD image
```

Each environment may require a different image.

With ConfigMaps and Secrets:

```text
             same Docker image
                    ↓
        stefanbobal/fake-sap-api:v3
             ↓        ↓        ↓
            DEV      QAS      PRD
             ↓        ↓        ↓
         ConfigMap ConfigMap ConfigMap
```

The same application image can be reused in multiple environments.

Only the runtime configuration changes.

---

## 14. Test a Configuration Change

Edit:

```text
configmap.yaml
```

For example change:

```yaml
DB_STATUS: "DOWN"
```

to:

```yaml
DB_STATUS: "UP"
```

Apply the ConfigMap again:

```bash
sudo kubectl apply -f configmap.yaml
```

Important:

Environment variables are injected when the Pod starts.

Existing Pods do not automatically reload environment variables from the ConfigMap.

Restart the Deployment:

```bash
sudo kubectl rollout restart deployment/fake-sap-api
```

Wait for rollout:

```bash
sudo kubectl rollout status deployment/fake-sap-api
```

Test again:

```bash
curl http://<SERVICE-IP>:8000/status
```

The response should now contain:

```json
"database": "UP"
```

---

## 15. Useful Commands

List ConfigMaps:

```bash
sudo kubectl get configmaps
```

Describe ConfigMap:

```bash
sudo kubectl describe configmap fake-sap-api-config
```

List Secrets:

```bash
sudo kubectl get secrets
```

Describe Secret:

```bash
sudo kubectl describe secret fake-sap-api-secret
```

Apply ConfigMap:

```bash
sudo kubectl apply -f configmap.yaml
```

Apply Secret:

```bash
sudo kubectl apply -f secret.yaml
```

Apply Deployment:

```bash
sudo kubectl apply -f deployment.yaml
```

Restart Deployment:

```bash
sudo kubectl rollout restart deployment/fake-sap-api
```

Check rollout:

```bash
sudo kubectl rollout status deployment/fake-sap-api
```

Check Pods:

```bash
sudo kubectl get pods
```

Inspect environment variables:

```bash
sudo kubectl exec -it <pod-name> -- env
```

---

## Key Takeaways

- Application configuration should not be hardcoded into the Docker image.
- ConfigMaps store non-sensitive configuration.
- Secrets store sensitive configuration.
- Kubernetes can inject ConfigMaps and Secrets as environment variables.
- The same Docker image can be reused across different environments.
- Updating a ConfigMap does not automatically update environment variables in already running Pods.
- Pods must normally be restarted to receive updated environment variables.
- Base64 is encoding, not encryption.
- Plain Kubernetes Secrets should not be committed to a public Git repository.

---

## Next Step

The next lab will improve Secret management using:

```text
Sealed Secrets
kubeseal
```

The workflow will become:

```text
plain Secret
   ↓
kubeseal
   ↓
encrypted SealedSecret
   ↓
GitHub
   ↓
Kubernetes
```

This allows encrypted Secret manifests to be safely stored in Git and later used with GitOps tools such as ArgoCD.
