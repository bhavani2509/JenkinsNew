pipeline {
  agent any  // your Windows node
  stages {
    stage('Test in Windows container') {
      steps {
        script {
          // Use ONE of these, matching your Windows version:
          // def img = docker.image('node:16-windowsservercore-ltsc2022')
          def img = docker.image('node:20-alpine')
          img.pull()
          img.inside {
            bat 'node --version'
          }
        }
      }
    }
  }
}
