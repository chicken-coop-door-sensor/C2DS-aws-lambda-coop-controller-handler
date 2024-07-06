# C2DS AWS Lambda Coop Controller Handler

The `C2DS-aws-lambda-coop-controller-handler` is a critical component of the Chicken Coop Door Sensor (C2DS) project.
This AWS Lambda function is responsible for assessing the state of the chicken coop door based on messages received from
the Coop Controller and determining if any error conditions exist that require user notification.

## Overview

The Coop Controller Handler (CCH) Lambda function receives door status messages from the Coop Controller, assesses the
state of the door, and triggers appropriate alerts if necessary. The CCH uses sunrise and sunset times, stored in a
DynamoDB table, to determine whether the coop door is in an acceptable state based on the time of day.

## Features

- Receives and processes door status messages (`OPEN`, `CLOSED`, `ERROR`) from the Coop Controller.
- Compares the current door status with the time of day to assess if the state is acceptable.
- Triggers alerts for various error conditions such as door closure failure at sunset, door open failure at sunrise, and
  sensor failures.
- Publishes the assessed state to the `coop/status` MQTT topic, which is subscribed to by the Coop Controller and Coop
  Snooper for LED status updates.

## Error Conditions

The CCH Lambda function handles the following error conditions and triggers notifications accordingly:

- **Door closure failure at sunset**: Indicates the door did not close at sunset.
- **Door open failure at sunrise**: Indicates the door did not open at sunrise.
- **Missing keep-alive messages**: Indicates a potential failure of the Coop Controller.
- **Sunrise/Sunset times retrieval failure**: Indicates an issue retrieving twilight times.
- **Status disagreement between optocouplers**: Indicates a potential connectivity problem with the Coop Controller.

## Dependencies

- **AWS IoT Core**: Manages communication between the Coop Controller, Coop Snooper, and the AWS cloud.
- **AWS Lambda**: Hosts the CCH function for processing door status messages.
- **AWS DynamoDB**: Stores the latest coop state and twilight times.
- **AWS S3**: Hosts OTA images for the Coop Controller and Coop Snooper.

## Repository Structure

- **lambda/**: Contains the source code for the Lambda function.
- **test/**: Contains test scripts and configurations.
- **README.md**: This file, providing an overview and details about the project.

## Getting Started

### Prerequisites

- AWS account with IoT Core, Lambda, DynamoDB, and S3 services configured.
- ESP32-based Coop Controller and Coop Snooper devices set up and registered as IoT Things.

### Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/yourusername/C2DS-aws-lambda-coop-controller-handler.git
    cd C2DS-aws-lambda-coop-controller-handler
    ```

2. Deploy the Lambda function using the AWS CLI or AWS Management Console.

### Configuration

- Ensure the Coop Controller publishes door status messages to the `coop/hardware/signal` MQTT topic.
- Subscribe the Coop Controller and Coop Snooper to the `coop/status` MQTT topic for status updates.
- Configure DynamoDB tables for storing twilight times and the latest coop state.

## Usage

The CCH Lambda function runs automatically in response to messages published to the `coop/hardware/signal` MQTT topic.
It processes these messages, assesses the door state, and triggers alerts as needed.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request with your changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

- ESP32-based Coop Controller and Coop Snooper hardware
- AWS IoT Core, Lambda, DynamoDB, and S3 services

For more information, please refer to the project documentation or contact the maintainer.

