# Meteo-App-Backend

Weather app backend running with Docker and Ansible. Supports Redis, MongoDB and exposes FastAPI backend via Uvicorn.

---

## 🛠 Tech stack

- Python 3.11, FastAPI  
- Redis 7  
- MongoDB 6  
- Docker, Ansible  
- uvicorn  

---

## 🚀 Run locally with Docker Compose

Make sure Docker network `shared-net` exists:

```bash
docker network create shared-net
```

Then build all services:

```bash
docker compose build
```

---

## 📦 Build & Push Docker image

```bash
docker login registry.cbpio.pl
docker build -t registry.cbpio.pl/username/weather-app:latest .
docker push registry.cbpio.pl/username/weather-app:latest
```

---

## ⚙️ Deploy with Ansible

Run the playbook using official Ansible container, mounting your playbooks and SSH key:

```bash
docker run --rm -it \
  -v /home/user/services/connect_moria:/ansible/playbooks \
  -v ~/.ssh/id_rsa:/root/.ssh/id_rsa:ro \
  willhallonline/ansible:latest \
  /bin/sh -c "ansible-galaxy install geerlingguy.docker && ansible-playbook -i /ansible/playbooks/hosts.ini /ansible/playbooks/meteo_setup.yml"
```

---

