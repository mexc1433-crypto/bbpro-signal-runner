#!/bin/bash
# ============================================================
# BBPro Signal Bot — Termux Setup Script
# ============================================================

echo "============================================"
echo "  BBPro Signal Bot — Termux Setup"
echo "============================================"

# 1. Install Termux packages
echo "[1/6] Installing system packages..."
pkg update -y && pkg upgrade -y
pkg install -y python python-pip git curl wget termux-api openssh

# 2. Set up auto-start on boot
echo ""
echo "[2/6] Setting up auto-start on boot..."
mkdir -p ~/.termux/boot

# 3. Grant wake lock
echo ""
echo "[3/6] Acquiring wake lock..."
termux-wake-lock 2>/dev/null || echo "  (Install Termux:API app from Play Store for wake lock)"

# 4. Clone repo
echo ""
echo "[4/6] Cloning repository..."
BOT_DIR="$HOME/bbpro-signal-bot"
if [ -d "$BOT_DIR" ]; then
    echo "  Repository exists. Pulling latest..."
    cd "$BOT_DIR"
    git pull origin main
else
    git clone https://github.com/your-username/bbpro-signal-bot.git "$BOT_DIR"
fi

# 5. Install Python dependencies
echo ""
echo "[5/6] Installing Python dependencies..."
cd "$BOT_DIR"
pip install --upgrade pip
pip install -r requirements.txt

# 6. Create .env file
echo ""
echo "[6/6] Setting up environment variables..."
if [ ! -f "$BOT_DIR/.env" ]; then
    cp "$BOT_DIR/.env.example" "$BOT_DIR/.env"
    echo "  Created .env file from template — edit it with your tokens!"
    echo "  Run: nano $BOT_DIR/.env"
else
    echo "  .env already exists."
fi

# Create boot script
cat > ~/.termux/boot/start-bbpro.sh << 'BOOTEOF'
#!/bin/bash
termux-wake-lock
sleep 10
bash ~/bbpro-signal-bot/termux/start_bot.sh
BOOTEOF
chmod +x ~/.termux/boot/start-bbpro.sh
chmod +x "$BOT_DIR/termux/start_bot.sh"

echo ""
echo "============================================"
echo "  ✅ Setup Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "1. Edit your tokens:  nano ~/bbpro-signal-bot/.env"
echo "2. Start the bot:     bash ~/bbpro-signal-bot/termux/start_bot.sh"
echo ""
echo "⚠️ Disable battery optimization for Termux:"
echo "   Settings > Apps > Termux > Battery > Unrestricted"
