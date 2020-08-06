# iot-device-simulator

Google Cloud Platform IoT Device Simulator

The following GCP components/services are involved:

-   Compute Engine (`f1-micro` machine type)
-   IoT Core service
-   PubSub service

## Prerequisites

-   GCP user account with necessary permissions
-   `gcloud` command installed and properly configured

## Getting Up and Running

Open a terminal at the project root:

-   Set environment variables in `.env` file (see `.env.example`).

-   Run `./gcp-init.sh --confirm` to perform GCP infrastructure initial setup.

-   Run `./create-iot-device.sh` with optional device ID argument, e.g.:

        $ ./create-iot-device.sh my-device

    by default `GCP_DEVICE_ID` value from `.env` file is used.

-   Run `./run-iot-device.sh` with optional device ID argument, e.g.:

        $ ./run-iot-device.sh my-device

    by default `GCP_DEVICE_ID` value from `.env` file is used.
 
You can run multiple instances of the device with different device ids.
 
 ## TODO
 
- [ ] Add ability to run fake iot device in a background
- [ ] Use Docker containers to ship python code
- [ ] Use API calls instead of using `gcloud` (someday)
- [ ] Create Web application to manage fake iot devices (someday)
