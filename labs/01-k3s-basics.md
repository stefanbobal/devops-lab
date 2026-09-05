# Lab 01 - K3s Basics

## Goal

Learn the basic Kubernetes concepts:

- Cluster
- Node
- Deployment
- Pod
- Container
- Image
- Replica
- Self-healing

---

## 1. Install k3s

Install k3s:

```bash
curl -sfL https://get.k3s.io | sh -

Check the Kubernetes node:

sudo kubectl get nodes

Expected result:

NAME      STATUS   ROLES           VERSION
k8s-lab   Ready    control-plane   v1.36.4+k3s1

2. Create a Deployment
Create an nginx Deployment:

sudo kubectl create deployment nginx --image=nginx

This tells Kubernetes to create a Deployment called nginx using the nginx container image.

Check the Deployment:

sudo kubectl get deployments

Check the Pods:

sudo kubectl get pods

3. Kubernetes object relationship
The basic relationship is:

Deployment
    ↓
Pod
    ↓
Container
    ↓
Image

In this lab:

nginx Deployment
    ↓
nginx Pod
    ↓
nginx container
    ↓
nginx image

4. Scale the Deployment
Scale nginx from one Pod to three Pods:

sudo kubectl scale deployment nginx --replicas=3

Check the Pods:

sudo kubectl get pods

There should now be three running Pods.

5. Test Kubernetes self-healing
Delete one Pod:

sudo kubectl delete pod <pod-name>

Example:

sudo kubectl delete pod nginx-7f8fbb96d-sgjqf

Check the Pods again:

sudo kubectl get pods

Kubernetes automatically creates a replacement Pod.

desired replicas = 3
actual replicas = 2

Kubernetes detects the difference and creates another Pod until:

desired replicas = 3
actual replicas = 3


Key concepts

Cluster
The complete Kubernetes environment.

Node
A server or virtual machine where Kubernetes workloads run.
In this lab, k8s-lab is both the control-plane and worker node.

Image
A packaged application.

Example:
nginx

Container
A running instance created from an image.

Pod
The smallest deployable unit in Kubernetes.
A Pod normally contains one application container.

Deployment
Defines how an application should run and how many replicas should exist.

Replica
One copy of a Pod.

Self-healing
If a Pod disappears or crashes, Kubernetes creates a replacement to maintain the desired state.


Example:
sapops@k8s-lab:~/devops-lab$ sudo kubectl create deployment nginx --image=nginx
deployment.apps/nginx created
sapops@k8s-lab:~/devops-lab$ sudo kubectl get deployments
sudo kubectl get pods
NAME    READY   UP-TO-DATE   AVAILABLE   AGE
nginx   0/1     1            0           9s
NAME                    READY   STATUS              RESTARTS   AGE
nginx-7f8fbb96d-sgjqf   0/1     ContainerCreating   0          9s
sapops@k8s-lab:~/devops-lab$ sudo kubectl get pods
NAME                    READY   STATUS    RESTARTS   AGE
nginx-7f8fbb96d-sgjqf   1/1     Running   0          27s
sapops@k8s-lab:~/devops-lab$ sudo kubectl scale deployment nginx --replicas=3
deployment.apps/nginx scaled
sapops@k8s-lab:~/devops-lab$ sudo kubectl get pods
NAME                    READY   STATUS    RESTARTS   AGE
nginx-7f8fbb96d-2c74g   1/1     Running   0          8s
nginx-7f8fbb96d-8mr9l   1/1     Running   0          8s
nginx-7f8fbb96d-sgjqf   1/1     Running   0          54s
sapops@k8s-lab:~/devops-lab$ sudo kubectl delete pod nginx-7f8fbb96d-sgjqf
pod "nginx-7f8fbb96d-sgjqf" deleted from default namespace
sapops@k8s-lab:~/devops-lab$ sudo kubectl get pods
NAME                    READY   STATUS    RESTARTS   AGE
nginx-7f8fbb96d-2c74g   1/1     Running   0          42s
nginx-7f8fbb96d-8mr9l   1/1     Running   0          42s
nginx-7f8fbb96d-xfrzv   1/1     Running   0          11s
sapops@k8s-lab:~/devops-lab$ 