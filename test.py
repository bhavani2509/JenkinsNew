This Bash script automates the build and execution of k6 load tests inside Docker, with test results exported to Elasticsearch and Prometheus for monitoring and analysis.

The script first defines default configuration values such as the target application URL, Elasticsearch credentials, and the index name where test metrics will be stored. It then builds the k6 JavaScript test bundle using npm run build, producing compiled test files in the dist/ directory.

Next, a custom k6 Docker image is built using Dockerfile.runner. This image includes additional k6 output extensions, enabling support for Elasticsearch output and Prometheus remote write.

The script then runs k6 inside a Docker container. The container:
	•	Mounts the compiled test files in read-only mode
	•	Connects to a predefined Docker network so it can access the application and Elasticsearch
	•	Passes required configuration via environment variables
	•	Automatically removes itself after test execution

During execution, k6 runs the specified test script and streams performance metrics simultaneously to:
	•	Elasticsearch (for long-term storage, search, and dashboards)
	•	Prometheus (for real-time monitoring and alerting)

Overall, this setup provides a repeatable, CI/CD-friendly, containerized performance testing framework with centralized observability, making it suitable for production-grade load testing and monitoring workflows.
