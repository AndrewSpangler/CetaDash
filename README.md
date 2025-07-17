# CetaDash

**CetaDash** is an extensible Docker orchestration system focused on **multi-step workflows**, **component reusability**, and **dynamic environment layering**. Built for simplicity and flexibility, CetaDash allows you to spin up containerized services and scripts through a clean, templated workflow engine.

---

## ⚠️ Disclaimer!

CetaDash is very early in development.
Use at your own risk and make sure to follow best practices with backups. 


---

## 🚀 Overview

CetaDash structures orchestration into modular, reusable building blocks. Workflows are composed of **Tasks**, which in turn can run Docker Compose templates or containerized **Scripts**. The system supports layered variable injection for easy configuration and overrides. 

---

## 📦 Features

* ✅ Designed for automation, CI/CD pipelines, homelabs, and data processing flows
* ✅ Rich templating and environment layering
* ✅ Seamless Docker Compose & Script execution
* ✅ Easy integration with triggers, schedules, and (soon) event listeners
* ✅ Customizable UI with independently configurable UI and Code Editor.
* ✅ Manage your Docker stack (without the Portainer pay-me-for-features hassl)
* ✅ Written in Python and WTFScript easily extended through Flask blueprinting. 
* ✅ Built in internal database viewer.
* ✅ Uses proxy-authentication through a trusted proxy to handle user access / management.

## 🧹 Orchestration Components

Each orchestration component supports an associated **Environment**, providing an extensible way to pass environment variables through the stack. Variable precedence follows a **top-down** model:

> **Trigger / Schedule → Workflow → Task → Script**

### 📜 Scripts

* The lowest-level executable component in CetaDash.
* Can be containerized and run inside a workflow.
* Ideal for lightweight jobs such as API calls, notifications, data munging, etc.
* Currently supports **Python**, with future plans for **Bash**, **JavaScript**, **PowerShell**, and **Lua**.

### ⚙️ Tasks

* A task is a reusable unit within a workflow.
* Can either:

  * Use a **templated Docker Compose file**, or
  * Run a selected **Script**.
* Tasks support templating and are designed for modular use across workflows.

### 🔁 Workflows

* A collection of ordered **Tasks**.
* Reusable across different **Triggers** or **Schedules**.
* Executes each task in sequence with inherited and overridden environment variables.

### 🚨 Triggers

* Automatically start a **Workflow** when a POST request hits a defined **Endpoint**.
* Triggers can extract HTTP headers and translate them into environment variables.
* Each trigger is tied to a route at:
  `HOST/endpoints/<endpoint_name>`

### 🌐 Endpoints

* Managed via **Triggers**.
* Accessible over HTTP at the `/endpoints/` path.
* On `POST`, executes the associated workflow and streams back execution logs.
* `GET` support for interactive form input is planned.

### ⏱️ Schedules

* Powered by **APScheduler**.
* Offers both **interval** and **Cron-style** scheduling for workflows.
* Easily manage time-based automation via a simple UI.

### 📢 Listeners *(Planned)*

* Watch for events in the database and run workflows automatically.
* Useful for cases like:

  * Running onboarding scripts when a user logs in for the first time.
  * Automating stateful backend logic based on real-time activity.

---

## 🛠️ Technologies

### Backend

* Traefik Proxy
* Authelia
* Docker + Compose

* **Python**

  * Flask
  * SQLAlchemy
  * APScheduler
  * Jinja2
  * WebTemplateForms / WTFScript (custom templating & workflow DSL)


### Frontend

* Bootstrap (with Bootswatch themes)
* CodeMirror (Code editor)
* SimpleMDE (Markdown editor)
* JSDataTables (for tabular data)
* Dragabbles.js

---

## 📅 Planned Features

* Database **Event Listeners** to power reactive workflows.
* Built-in **Documentation Module** (Docu Plugin) to attach help, API usage, and maintenance notes directly to orchestration components — perfect for homelab and team use.

---

Let us know if you'd like to contribute, extend, or customize CetaDash for your own needs!
