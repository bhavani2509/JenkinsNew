name: Maintenance Failover Scheduler

on:
  schedule:
    # Trigger 1: 30 mins before Cluster 1 Maint (05:00). Runs at 04:30 UTC.
    - cron: '30 4 * * 0'
    # Trigger 2: 30 mins before Cluster 2 Maint (10:00). Runs at 09:30 UTC.
    - cron: '30 9 * * 0'
  workflow_dispatch:

env:
  APPLICATION: "esp"
  LIFECYCLE: "prod"
  RG_NAME: "app-dns-prod-eastus2"
  TTL: 300

jobs:
  failover:
    runs-on: on-prem
    steps:
      - name: Determine Target Cluster
        id: target
        run: |
          current_hour=$(date -u +%H)
          # If it's the 04:00 hour (UTC), Cluster 1 is about to patch. Switch to Cluster 2.
          if [ "$current_hour" -eq "04" ]; then
            echo "CLUSTER=2" >> $GITHUB_ENV
            echo "Switching traffic to Cluster 2 (Secondary)."
          # If it's the 09:00 hour (UTC), Cluster 2 is about to patch. Switch to Cluster 1.
          elif [ "$current_hour" -eq "09" ]; then
            echo "CLUSTER=1" >> $GITHUB_ENV
            echo "Switching traffic back to Cluster 1 (Primary)."
          else
            echo "Error: Workflow triggered at unexpected time ($current_hour UTC)."
            exit 1
          fi

      - name: Read vault secrets
        uses: hashicorp/vault-action@v2.4.1
        with:
          url: https://vault.cluster.us-vault-prod.azure.lnrsg.io/
          method: approle
          roleId: ${{ secrets.ROLE_ID }}
          secretId: ${{ secrets.ROLE_SECRET }}
          namespace: "businessservices/${{ env.APPLICATION }}/${{ env.LIFECYCLE }}"
          exportToken: true
          secrets: |
            static_secrets/service_principle Application_ID | SP_APP_ID ;
            static_secrets/service_principle Secret | SP_SECRET ;
            static_secrets/service_principle Tenant_ID | SP_TENANT_ID ;

      - name: Azure login
        run: |
          az login --service-principal -u "${{ steps.vault.outputs.SP_APP_ID }}" -p "${{ steps.vault.outputs.SP_SECRET }}" --tenant "${{ steps.vault.outputs.SP_TENANT_ID }}"
          az account set --subscription "us-${{ env.APPLICATION }}-${{ env.LIFECYCLE }}"

      - name: Update DNS Records
        run: |
          zone_name="us-${{ env.APPLICATION }}-${{ env.LIFECYCLE }}.azure.lnrsg.io"
          
          # Records to update
          records=("ws" "wsbatch" "wsonline" "wsonline80" "wswaf" "phiauth")
          
          for record in "${records[@]}"; do
            echo "Updating $record to point to cluster ${{ env.CLUSTER }}..."
            az network dns record-set cname update \
              -g ${{ env.RG_NAME }} \
              -z $zone_name \
              -n "$record" \
              --set CNAME="$record-${{ env.CLUSTER }}.$zone_name" \
              --ttl ${{ env.TTL }}
          done

      - name: Send Notification
        uses: dawidd6/action-send-mail@v3
        if: always()
        with:
          server_address: app-mail-eastus.us.globalegress-prod.azure.lnrsg.io
          server_port: 25
          subject: "Maintenance Failover: Traffic Moved to Cluster ${{ env.CLUSTER }}"
          body: |
            The automated maintenance scheduler has moved traffic for ${{ env.APPLICATION }} ${{ env.LIFECYCLE }}.
            Target Cluster: ${{ env.CLUSTER }}
            Trigger Time: $(date)
          to: "team-alerts@example.com"
          from: "noreply@lexisnexisrisk.com"
