# Zealy Instagram Monitor - Deployment Guide

## 🚀 Quick Deployment Options

### **Option 1: DigitalOcean Droplet (Recommended)**
```bash
# 1. Create Ubuntu 22.04 droplet
# 2. Connect via SSH
sudo apt update && sudo apt upgrade -y

# 3. Install Python and pip
sudo apt install python3 python3-pip python3-venv -y

# 4. Clone your repository
git clone https://github.com/callmedraxx/Zealy_Monitor.git
cd Zealy_Monitor

# 5. Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# 6. Install dependencies
pip install -r requirements.txt

# 7. Create .env file with your credentials
nano .env

# 8. Run the application
python claim_insta.py
```

### **Option 2: AWS EC2**
```bash
# 1. Launch Ubuntu EC2 instance
# 2. Configure security group (open port 5000)
# 3. Connect via SSH
sudo apt update && sudo apt install python3 python3-pip -y

# 4. Follow steps 4-8 from DigitalOcean guide above
```

### **Option 3: Google Cloud Compute Engine**
```bash
# 1. Create Ubuntu VM instance
# 2. Configure firewall (allow TCP:5000)
# 3. Follow same installation steps
```

### **Option 4: Using Docker (Advanced)**
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["python", "claim_insta.py"]
```

## 🌐 Access Your Web Interface

Once deployed, access your upload page at:
```
http://YOUR_SERVER_IP:5000
```

### **Find Your Server IP:**
- **DigitalOcean**: Dashboard → Droplets → Your droplet → IPv4
- **AWS EC2**: EC2 Dashboard → Instances → Public IPv4 address
- **Google Cloud**: Compute Engine → VM instances → External IP

## ⚠️ Important Security Notes

Since you mentioned no security needed, here are the implications:

### **✅ What's Working:**
- ✅ Public access from any device
- ✅ No authentication required
- ✅ Simple file upload interface

### **⚠️ Security Considerations:**
- **Anyone** with the URL can upload files to your server
- **Anyone** can see your upload form
- Uploaded images are stored on your server
- No rate limiting or abuse protection

### **🔒 If You Change Your Mind About Security:**
Consider adding:
- Basic authentication
- IP whitelisting
- Rate limiting
- HTTPS (SSL certificate)

## 🛠️ Troubleshooting

### **Port Already in Use:**
```bash
# Change port in claim_insta.py
flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False), daemon=True)
```

### **Firewall Issues:**
```bash
# Ubuntu/Debian
sudo ufw allow 5000

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=5000/tcp
sudo firewall-cmd --reload
```

### **Keep App Running After SSH Disconnect:**
```bash
# Using screen
sudo apt install screen -y
screen -S zealy
python claim_insta.py
# Press Ctrl+A, D to detach
# Reconnect: screen -r zealy

# Using nohup
nohup python claim_insta.py &
```

## 🎯 Your Web Interface Features

- **Upload Form**: `http://YOUR_SERVER_IP:5000`
- **Account Name**: Text field for account identifier
- **Instagram Link**: URL of the Instagram post
- **Image Upload**: Two file inputs for screenshots
- **Automatic Processing**: Links are stored and matched against Instagram tasks

## 📱 Mobile Access

The interface works perfectly on mobile devices - simply visit the URL from your phone's browser!

---

**Your Flask app is already configured for public access!** Just deploy to any cloud server and you'll be able to access the upload page from anywhere. 🌍</content>
<parameter name="filePath">/Users/0xsigma/pytest/DEPLOYMENT_GUIDE.md
