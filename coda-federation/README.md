<h2 align="center">What is Vantage6?</h2>

Vantage6 is an open-source federated learning architecture that allows several parties to work together to analyse and train models while maintaining local data sovereignty and privacy.

**Fundamental Components:**

- **Server:** Orchestrates collaborations, tasks, and users.  
- **Node:** Runs at each data-holding organization and executes algorithms on local data.  
- **Algorithm:** Containerized code (typically in Docker) sent to nodes for computation.

---

## 🔧 Requirements

- **Operating System:** Linux, macOS, or Windows  
- **Python:** 3.7+  
- **Docker:** Installed and running (latest stable version)  
- **(Recommended)**: Python virtual environment (`venv` or `conda`)

---

## Setup Steps

### 1. Create and Activate a Virtual Environmentss
python3 -m venv vantage

source vantage/bin/activate

### 2. Install Vantage6

pip install vantage6

Optionally, check installed packages:

pip list


### 3. Create the Demo Network

v6 dev create-demo-network --server-url http://172.17.0.1 

This will create a demo network with 1 server and 3 nodes.

### 4. Start the Demo Network

v6 dev start-demo-network


### 5. Check Node Logs

To view logs for a specific node:

v6 node attach --name


## Access the Vantage6 Web Interface

- Open your browser and navigate to:  
  `http://localhost:7600/#/`
- Log in:
  - **Username:** dev_admin
  - **Password:** password

You should see the Vantage6 user interface.

## Notes

- The provided commands create a demo environment with 3 nodes and 1 server.
- You can inspect, manage, and interact with the network using both the CLI and the web interface.
- For further customization and documentation, visit the [Vantage6 documentation](https://docs.vantage6.ai/).


## Creating a New Organization with Vantage6 Python Client


from vantage6.client import Client

### Initialize the client with server address and port

client = Client('http://127.0.0.1', 7601, '/api', log_level='debug')


### Authenticate with username and password
client.authenticate('dev_admin', 'password')

### Setup encryption (use None if no encryption key)
client.setup_encryption(None)


client = Client('http://127.0.0.1', 7601, '/api', log_level='debug')

### Create a new organization
client.organization.create(
name='My organization',
address1='My address',
address2='My address',
zipcode='1234AB',
country='',
domain='my-organization.com'
)
