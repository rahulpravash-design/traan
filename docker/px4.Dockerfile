# PX4 SITL, SIH (headless, no Gazebo). Heavy: ~20 min and ~8 GB disk to build the first time.
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
ARG PX4_TAG=v1.15.4
RUN apt-get update && apt-get install -y --no-install-recommends git sudo ca-certificates python3-pip lsb-release \
 && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch ${PX4_TAG} --recursive https://github.com/PX4/PX4-Autopilot.git /px4
RUN bash /px4/Tools/setup/ubuntu.sh --no-sim-tools --no-nuttx && rm -rf /var/lib/apt/lists/*
RUN cd /px4 && make px4_sitl_default
COPY fleet/px4_sitl.sh /px4_sitl.sh
ENV PX4_DIR=/px4 WORK_DIR=/tmp/px4_instances
CMD ["bash", "/px4_sitl.sh", "3"]
