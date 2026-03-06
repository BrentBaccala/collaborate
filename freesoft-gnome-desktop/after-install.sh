#!/bin/bash -e

dconf update

# Disable release upgrade prompts (BBB requires Ubuntu 22.04)
sed -i 's/^Prompt=.*/Prompt=never/' /etc/update-manager/release-upgrades

# Add the gnome-shell-extensions PPA for dash-to-panel (if not already configured).
if ! grep -q 'gnome-shell-extensions/ppa' /etc/apt/sources.list.d/*.list 2>/dev/null; then
    add-apt-repository -y ppa:gnome-shell-extensions/ppa
fi

# Install dash-to-panel if not already installed.
# Since this postinst runs inside dpkg (which holds the dpkg lock), we can't
# call apt-get directly. Instead, schedule the install via a systemd oneshot
# service that runs on next boot (or immediately if we're not inside dpkg).
if ! dpkg -s gnome-shell-extension-dash-to-panel >/dev/null 2>&1; then
    cat > /etc/systemd/system/install-dash-to-panel.service <<'EOF'
[Unit]
Description=Install dash-to-panel GNOME extension
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/usr/share/gnome-shell/extensions/dash-to-panel@jderose9.github.com

[Service]
Type=oneshot
ExecStart=/bin/bash -c "apt-get update -y && apt-get install -y gnome-shell-extension-dash-to-panel && systemctl disable install-dash-to-panel.service"
RemainAfterExit=true

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable install-dash-to-panel.service
    # Try to start it now; if dpkg lock is held, it will run on next boot
    systemctl start install-dash-to-panel.service 2>/dev/null || true
fi
