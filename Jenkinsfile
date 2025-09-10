pipeline {
    agent any

    stages {
        stage('Check Docker') {
            steps {
                bat 'docker version'
            }
        }

        stage('Run Node Container') {
            steps {
                // Pull and run a quick Node container to print versions
                bat '''
                    docker pull node:20-alpine
                    docker run --rm node:20-alpine node -v
                    docker run --rm node:20-alpine npm -v
                '''
            }
        }
    }
}
