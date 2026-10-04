import os

bashrc_path = os.path.expanduser("~/.bashrc")
with open(bashrc_path, "r", encoding="utf-8") as f:
    bashrc = f.read()

# Filter out old cache exports and insightex_env.sh
lines = []
for line in bashrc.splitlines():
    if "/mnt/e/FYP/cache" in line or "insightex_env.sh" in line:
        continue
    lines.append(line)

# Put source at the top and at the bottom
new_bashrc = "source /mnt/e/FYP/env/insightex_env.sh\n" + "\n".join(lines) + "\nsource /mnt/e/FYP/env/insightex_env.sh\n"
with open(bashrc_path, "w", encoding="utf-8") as f:
    f.write(new_bashrc)

profile_path = os.path.expanduser("~/.profile")
if os.path.exists(profile_path):
    with open(profile_path, "r", encoding="utf-8") as f:
        profile = f.read()
    if "insightex_env.sh" not in profile:
        with open(profile_path, "a", encoding="utf-8") as f:
            f.write("\nsource /mnt/e/FYP/env/insightex_env.sh\n")

print("Successfully updated ~/.bashrc and ~/.profile")
