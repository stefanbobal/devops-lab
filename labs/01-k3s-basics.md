# Lab 01 - K3s Basics

## Goal

Learn the basic Kubernetes concepts and deploy the first containerized application.

Topics covered:

- Cluster
- Node
- Image
- Container
- Pod
- Deployment
- Replica
- Scaling
- Self-healing

---

## Environment

- Host OS: Windows
- Hypervisor: VirtualBox
- Guest OS: Ubuntu Server
- Kubernetes distribution: k3s
- Development environment: VS Code Remote SSH

---

## 1. Install k3s

Install k3s:

```bash
curl -sfL https://get.k3s.io | sh -
```

Check the Kubernetes node:

```bash
sudo kubectl get nodes
```

Example output:

```text
NAME      STATUS   ROLES           AGE   VERSION
k8s-lab   Ready    control-plane   10s   v1.36.4+k3s1
```

---

## 2. Basic Kubernetes Concepts

### Cluster

A Kubernetes cluster is the complete Kubernetes environment.

It contains the control plane and one or more worker nodes.

In this lab, the entire cluster runs on a single virtual machine.

---

### Node

A node is a server or virtual machine where Kubernetes workloads run.

In this lab:

```text
k8s-lab
```

is both the control-plane and worker node.

---

### Image

An image is a packaged application and all dependencies required to run it.

Example:

```text
nginx
```

The nginx image contains the nginx web server and everything required to execute it inside a container.

---

### Container

A container is a running instance created from an image.

The relationship is:

```text
Image
  ↓
Container
```

For example:

```text
nginx image
    ↓
running nginx container
```

---

### Pod

A Pod is the smallest deployable unit in Kubernetes.

A Pod normally contains one application container.

Example:

```text
Pod
└── nginx container
```

A Pod can technically contain multiple containers, but the common pattern is one main application container per Pod.

---

### Deployment

A Deployment defines how an application should run and how many Pod replicas should exist.

Example:

```text
Deployment
   ↓
Pod
   ↓
Container
   ↓
Image
```

In this lab:

```text
nginx Deployment
       ↓
nginx Pod
       ↓
nginx container
       ↓
nginx image
```

---

### Replica

A replica is one copy of a Pod.

For example:

```text
Deployment
├── Pod 1
├── Pod 2
└── Pod 3
```

Multiple replicas can improve availability and allow an application to process more requests in parallel.

---

### Self-healing

Kubernetes continuously compares the desired state with the actual state.

For example:

```text
Desired replicas = 3
Actual replicas  = 2
```

Kubernetes detects the difference and automatically creates another Pod.

Eventually:

```text
Desired replicas = 3
Actual replicas  = 3
```

---

## 3. Create the First Deployment

Create an nginx Deployment:

```bash
sudo kubectl create deployment nginx --image=nginx
```

Output:

```text
deployment.apps/nginx created
```

This command tells Kubernetes:

- create a Deployment called `nginx`
- use the `nginx` container image
- maintain the required number of Pods

Check the Deployment:

```bash
sudo kubectl get deployments
```

Example output:

```text
NAME    READY   UP-TO-DATE   AVAILABLE   AGE
nginx   0/1     1            0           9s
```

Check the Pods:

```bash
sudo kubectl get pods
```

During startup the Pod may initially appear as:

```text
NAME                    READY   STATUS              RESTARTS   AGE
nginx-7f8fbb96d-sgjqf   0/1     ContainerCreating   0          9s
```

A few seconds later:

```text
NAME                    READY   STATUS    RESTARTS   AGE
nginx-7f8fbb96d-sgjqf   1/1     Running   0          27s
```

The nginx application is now running inside a container inside a Kubernetes Pod.

---

## 4. Scale the Deployment

Scale the nginx Deployment from one replica to three replicas:

```bash
sudo kubectl scale deployment nginx --replicas=3
```

Output:

```text
deployment.apps/nginx scaled
```

Check the Pods:

```bash
sudo kubectl get pods
```

Example:

```text
NAME                    READY   STATUS    RESTARTS   AGE
nginx-7f8fbb96d-2c74g   1/1     Running   0          8s
nginx-7f8fbb96d-8mr9l   1/1     Running   0          8s
nginx-7f8fbb96d-sgjqf   1/1     Running   0          54s
```

There are now three nginx Pods running.

Conceptually:

```text
nginx Deployment
├── nginx Pod 1
├── nginx Pod 2
└── nginx Pod 3
```

---

## 5. Test Kubernetes Self-healing

Delete one Pod manually:

```bash
sudo kubectl delete pod nginx-7f8fbb96d-sgjqf
```

Output:

```text
pod "nginx-7f8fbb96d-sgjqf" deleted from default namespace
```

Check the Pods again:

```bash
sudo kubectl get pods
```

Example:

```text
NAME                    READY   STATUS    RESTARTS   AGE
nginx-7f8fbb96d-2c74g   1/1     Running   0          42s
nginx-7f8fbb96d-8mr9l   1/1     Running   0          42s
nginx-7f8fbb96d-xfrzv   1/1     Running   0          11s
```

The deleted Pod:

```text
nginx-7f8fbb96d-sgjqf
```

was automatically replaced by:

```text
nginx-7f8fbb96d-xfrzv
```

This happened because the Deployment still required three replicas.

Kubernetes detected:

```text
Desired state = 3 Pods
Actual state  = 2 Pods
```

and automatically created another Pod.

This behavior is called **self-healing**.

---

## 6. What Happened Internally

The simplified flow is:

```text
Deployment
   ↓
ReplicaSet
   ↓
Pods
   ↓
Containers
   ↓
nginx image
```

The Deployment defines the desired application state.

The ReplicaSet ensures the requested number of Pods exists.

Each Pod runs a container created from the nginx image.

---

## 7. Useful Commands

Check cluster nodes:

```bash
sudo kubectl get nodes
```

Check Deployments:

```bash
sudo kubectl get deployments
```

Check Pods:

```bash
sudo kubectl get pods
```

Show more information about Pods:

```bash
sudo kubectl get pods -o wide
```

Scale a Deployment:

```bash
sudo kubectl scale deployment nginx --replicas=3
```

Delete a Pod:

```bash
sudo kubectl delete pod <pod-name>
```

Show detailed information about a Pod:

```bash
sudo kubectl describe pod <pod-name>
```

Show container logs:

```bash
sudo kubectl logs <pod-name>
```

---

## Key Takeaways

- Kubernetes manages containerized applications.
- A Node is a machine where workloads run.
- An Image is a packaged application.
- A Container is a running instance of an image.
- A Pod is the smallest deployable Kubernetes unit.
- A Deployment manages Pods.
- Replicas allow multiple copies of an application to run.
- Kubernetes continuously maintains the desired state.
- If a Pod disappears, Kubernetes can automatically replace it.