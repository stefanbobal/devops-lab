# Lab 02 - Kubernetes Services

## Goal

Understand how Kubernetes Services provide stable network access to Pods.

Topics covered:

- Pod IP addresses
- Service
- ClusterIP
- Endpoints
- Service discovery
- Traffic routing
- Why Services are needed

---

## 1. Check Pod IP Addresses

Display Pods including their IP addresses:

```bash
sudo kubectl get pods -o wide
```

Example output:

```text
NAME                    READY   STATUS    RESTARTS   AGE   IP
nginx-7f8fbb96d-2c74g   1/1     Running   0          ...   10.42.0.10
nginx-7f8fbb96d-8mr9l   1/1     Running   0          ...   10.42.0.11
nginx-7f8fbb96d-xfrzv   1/1     Running   0          ...   10.42.0.12
```

Each Pod has its own IP address.

The problem is that Pod IP addresses are not permanent.

If a Pod is deleted and recreated, the new Pod may receive a different IP address.

Because of this, applications should normally not connect directly to individual Pod IP addresses.

---

## 2. Create a Kubernetes Service

Create a Service for the nginx Deployment:

```bash
sudo kubectl expose deployment nginx --port=80 --type=ClusterIP
```

This creates a Service called `nginx`.

The Service exposes port `80`, which is the HTTP port used by nginx.

---

## 3. Check the Service

Display Kubernetes Services:

```bash
sudo kubectl get services
```

Example output:

```text
NAME         TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)
kubernetes   ClusterIP   10.43.0.1       <none>        443/TCP
nginx        ClusterIP   10.43.123.45    <none>        80/TCP
```

The nginx Service receives a stable internal IP address.

Example:

```text
10.43.123.45
```

This IP belongs to the Service, not to a specific Pod.

---

## 4. Test the Service

Send an HTTP request to the Service IP:

```bash
curl http://<SERVICE-IP>
```

Example:

```bash
curl http://10.43.123.45
```

Expected response:

```html
<h1>Welcome to nginx!</h1>
```

This confirms that the request successfully reached one of the nginx Pods.

---

## 5. Traffic Flow

The simplified traffic flow is:

```text
Client
  ↓
nginx Service
  ↓
nginx Pods
  ↓
nginx containers
```

With three replicas:

```text
Client
  ↓
nginx Service
  ↓
├── nginx Pod 1
├── nginx Pod 2
└── nginx Pod 3
```

The client does not need to know which specific Pod handles the request.

The Service provides a stable endpoint in front of the Pods.

---

## 6. Check Service Endpoints

Display the endpoints used by the nginx Service:

```bash
sudo kubectl get endpoints nginx
```

Example output:

```text
NAME    ENDPOINTS
nginx   10.42.0.10:80,10.42.0.11:80,10.42.0.12:80
```

These IP addresses correspond to the nginx Pods.

The Service routes traffic to these backend endpoints.

A newer Kubernetes object used for the same purpose is `EndpointSlice`.

Check EndpointSlices:

```bash
sudo kubectl get endpointslices
```

---

## 7. Test Service Behavior After Pod Replacement

Display the current Pods and their IP addresses:

```bash
sudo kubectl get pods -o wide
```

Delete one Pod:

```bash
sudo kubectl delete pod <pod-name>
```

Example:

```bash
sudo kubectl delete pod nginx-7f8fbb96d-2c74g
```

Check the Pods again:

```bash
sudo kubectl get pods -o wide
```

Kubernetes creates a replacement Pod.

The new Pod may receive a different IP address.

Now check the Service endpoints again:

```bash
sudo kubectl get endpoints nginx
```

The old Pod IP disappears and the new Pod IP is automatically added.

The Service itself does not change.

---

## Why Services Are Needed

Without a Service:

```text
Application
   ↓
Pod IP
```

This is unreliable because the Pod may disappear and receive a new IP address.

With a Service:

```text
Application
   ↓
Stable Service IP
   ↓
Current healthy Pods
```

The Service gives clients a stable network endpoint while Kubernetes manages the changing Pods behind it.

---

## ClusterIP

`ClusterIP` is the default Kubernetes Service type.

A ClusterIP Service is reachable only from inside the Kubernetes cluster.

Example:

```text
TYPE: ClusterIP
IP:   10.43.123.45
PORT: 80
```

This is commonly used for communication between internal application components.

Example:

```text
frontend
   ↓
backend Service
   ↓
backend Pods
```

---

## Relationship Between Deployment, Pods and Service

```text
Deployment
   ↓
ReplicaSet
   ↓
Pods
   ↑
Service
```

The Deployment manages how many Pods should exist.

The Service provides stable network access to those Pods.

Together:

```text
Client
  ↓
Service
  ↓
Pods managed by Deployment
```

---

## Useful Commands

Show Services:

```bash
sudo kubectl get services
```

Show a specific Service:

```bash
sudo kubectl get service nginx
```

Show detailed Service information:

```bash
sudo kubectl describe service nginx
```

Show Pod IP addresses:

```bash
sudo kubectl get pods -o wide
```

Show Service endpoints:

```bash
sudo kubectl get endpoints nginx
```

Show EndpointSlices:

```bash
sudo kubectl get endpointslices
```

Test the Service:

```bash
curl http://<SERVICE-IP>
```

---

## Key Takeaways

- Every Pod has its own IP address.
- Pod IP addresses are temporary.
- A Service provides a stable network endpoint.
- `ClusterIP` is the default Service type.
- A Service can route traffic to multiple Pods.
- The Service automatically tracks the current Pod endpoints.
- Clients do not need to know individual Pod IP addresses.
- Pod replacement does not require clients to change the Service address.

## What I did in this lab:

```bash

sapops@k8s-lab:~/devops-lab$ sudo kubectl get pods -o wide
[sudo: authenticate] Password:            
NAME                    READY   STATUS    RESTARTS   AGE   IP           NODE      NOMINATED NODE   READINESS GATES
nginx-7f8fbb96d-2c74g   1/1     Running   0          23m   10.42.0.10   k8s-lab   <none>           <none>
nginx-7f8fbb96d-8mr9l   1/1     Running   0          23m   10.42.0.11   k8s-lab   <none>           <none>
nginx-7f8fbb96d-xfrzv   1/1     Running   0          23m   10.42.0.12   k8s-lab   <none>           <none>
sapops@k8s-lab:~/devops-lab$ sudo kubectl expose deployment nginx --port=80 --type=ClusterIP
service/nginx exposed
sapops@k8s-lab:~/devops-lab$ sudo kubectl get services
NAME         TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)   AGE
kubernetes   ClusterIP   10.43.0.1      <none>        443/TCP   35m
nginx        ClusterIP   10.43.95.201   <none>        80/TCP    10s
sapops@k8s-lab:~/devops-lab$ sudo kubectl get endpoints nginx
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME    ENDPOINTS                                   AGE
nginx   10.42.0.10:80,10.42.0.11:80,10.42.0.12:80   30s
sapops@k8s-lab:~/devops-lab$ sudo kubectl get endpointslices
NAME          ADDRESSTYPE   PORTS   ENDPOINTS                          AGE
kubernetes    IPv4          6443    192.168.178.110                    36m
nginx-pcvb6   IPv4          80      10.42.0.10,10.42.0.11,10.42.0.12   41s
sapops@k8s-lab:~/devops-lab$ curl http://10.42.0.10
<!DOCTYPE html>
<html>
<head>
<title>Welcome to nginx!</title>
<style>
html { color-scheme: light dark; }
body { width: 35em; margin: 0 auto;
font-family: Tahoma, Verdana, Arial, sans-serif; }
</style>
</head>
<body>
<h1>Welcome to nginx!</h1>
<p>If you see this page, nginx is successfully installed and working.
Further configuration is required for the web server, reverse proxy, 
API gateway, load balancer, content cache, or other features.</p>

<p>For online documentation and support please refer to
<a href="https://nginx.org/">nginx.org</a>.<br/>
To engage with the community please visit
<a href="https://community.nginx.org/">community.nginx.org</a>.<br/>
For enterprise grade support, professional services, additional 
security features and capabilities please refer to
<a href="https://f5.com/nginx">f5.com/nginx</a>.</p>

<p><em>Thank you for using nginx.</em></p>
</body>
</html>
sapops@k8s-lab:~/devops-lab$ sudo kubectl get pods -o wide
NAME                    READY   STATUS    RESTARTS   AGE   IP           NODE      NOMINATED NODE   READINESS GATES
nginx-7f8fbb96d-2c74g   1/1     Running   0          27m   10.42.0.10   k8s-lab   <none>           <none>
nginx-7f8fbb96d-8mr9l   1/1     Running   0          27m   10.42.0.11   k8s-lab   <none>           <none>
nginx-7f8fbb96d-xfrzv   1/1     Running   0          26m   10.42.0.12   k8s-lab   <none>           <none>
sapops@k8s-lab:~/devops-lab$ sudo kubectl get endpoints nginx
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME    ENDPOINTS                                   AGE
nginx   10.42.0.10:80,10.42.0.11:80,10.42.0.12:80   3m18s
sapops@k8s-lab:~/devops-lab$ sudo kubectl delete pod nginx-7f8fbb96d-2c74g
pod "nginx-7f8fbb96d-2c74g" deleted from default namespace
sapops@k8s-lab:~/devops-lab$ sudo kubectl get endpoints nginx
Warning: v1 Endpoints is deprecated in v1.33+; use discovery.k8s.io/v1 EndpointSlice
NAME    ENDPOINTS                                   AGE
nginx   10.42.0.11:80,10.42.0.12:80,10.42.0.13:80   3m56s
sapops@k8s-lab:~/devops-lab$ 