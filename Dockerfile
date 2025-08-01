# === FILE: Dockerfile ===

# Start from the pre-built image that already includes ffmpeg.
FROM linuxserver/ffmpeg

# Set the working directory inside the container
WORKDIR /app

# Install Python and other necessary system tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Create and activate a virtual environment to avoid OS conflicts.
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy and install Python dependencies into the virtual environment.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container.
COPY . .

# Make your startup script executable.
RUN chmod +x ./run.sh

# --- THE FINAL FIX ---
# The linuxserver/ffmpeg image defaults to running the 'ffmpeg' command.
# We override this entrypoint to ensure our startup script is run with a bash shell.
ENTRYPOINT ["/bin/bash", "-c"]

# This is the command that will now be executed correctly by the bash shell.
CMD ["./run.sh"]
