Task 1: Fix and Stagger Maintenance Schedules
Goal: Ensure two clusters (let's call them Blue and Green) do not patch at the same time. The current schedule is Sunday at 07:00 UTC (2 AM EST) for a duration of 4 hours.
Solution: Modify Terraform variables (.tfvars) so the second cluster's maintenance window starts after the first one finishes (plus a safety buffer).
Configuration for Cluster 1 (Blue) - Keep as is:
Terraform
# In bweb-blue.auto.tfvars (or similar)
maintenance_schedule = {
  control_plane = {
    day_of_week = "SUNDAY"
    start_time  = "07:00" # 2 AM EST
    duration    = 4
    frequency   = "WEEKLY"
  }
  nodes = {
    day_of_week = "SUNDAY"
    start_time  = "07:00"
    duration    = 4
    frequency   = "WEEKLY"
  }
}

Configuration for Cluster 2 (Green) - Offset by 6 hours:
Terraform
# In bweb-green.auto.tfvars (or similar)
maintenance_schedule = {
  control_plane = {
    day_of_week = "SUNDAY"
    start_time  = "13:00" # 8 AM EST (Safe: 2 hours after Blue finishes)
    duration    = 4
    frequency   = "WEEKLY"
  }
  nodes = {
    day_of_week = "SUNDAY"
    start_time  = "13:00"
    duration    = 4
    frequency   = "WEEKLY"
  }
}

________________________________________

Task 2: Write GitHub Actions for Auto-Switching
Goal: Create a workflow that runs on a schedule to switch traffic away from the cluster about to undergo maintenance.
Strategy:
1.	Trigger 1: Runs at 06:30 UTC (30 mins before Blue maintenance) -> Switches traffic to Green.
2.	Trigger 2: Runs at 12:30 UTC (30 mins before Green maintenance) -> Switches traffic to Blue.
Create a new file .github/workflows/maintenance-scheduler.yml. I have adapted the logic from your existing cluster-toggle.yml screenshots (specifically the vault auth, azure login, and DNS switching logic).

name: Maintenance Failover Scheduler
on:
  schedule:
    # Trigger at 06:30 UTC every Sunday (Before Blue Maint @ 07:00)
    - cron: '30 6 * * 0'
    # Trigger at 12:30 UTC every Sunday (Before Green Maint @ 13:00)
    - cron: '30 12 * * 0'
  workflow_dispatch: # Allow manual testing

env:
  # Common Env Vars extracted from your screenshots
  APPLICATION: "esp" 
  LIFECYCLE: "prod"
  TTL: 300
  RG_NAME: "app-dns-prod-eastus2"

jobs:
  switch-traffic:
    runs-on: on-prem # Matches your existing runner requirements
    steps:
      - name: Determine Target Cluster
        id: target
        run: |
          current_hour=$(date -u +%H)
          # If running near 06:00 UTC, we are prepping for Blue Maint, so switch to GREEN (Cluster 2)
          if [ "$current_hour" -eq 6 ]; then
            echo "CLUSTER=2" >> $GITHUB_ENV
            echo "Switching traffic to Cluster 2 (Green) in preparation for Cluster 1 maintenance."
          # If running near 12:00 UTC, we are prepping for Green Maint, so switch to BLUE (Cluster 1)
          elif [ "$current_hour" -eq 12 ]; then
            echo "CLUSTER=1" >> $GITHUB_ENV
            echo "Switching traffic to Cluster 1 (Blue) in preparation for Cluster 2 maintenance."
          else
             echo "Manual trigger or off-schedule. Defaulting to 1 (Safe fallback, check inputs if testing)"
             echo "CLUSTER=1" >> $GITHUB_ENV
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
          # Logic copied from image_7be45e.jpg
          curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
          az login --service-principal -u "${{ steps.vault.outputs.SP_APP_ID }}" -p "${{ steps.vault.outputs.SP_SECRET }}" --tenant "${{ steps.vault.outputs.SP_TENANT_ID }}"
          az account set --subscription "us-${{ env.APPLICATION }}-${{ env.LIFECYCLE }}"

      - name: Update DNS Records
        run: |
          zone_name="us-${{ env.APPLICATION }}-${{ env.LIFECYCLE }}.azure.lnrsg.io"
          
          echo "Updating DNS Zone: $zone_name in RG: ${{ env.RG_NAME }}"
          echo "Pointing records to Cluster: ${{ env.CLUSTER }}"

          # Logic adapted from image_7be45e.jpg and image_7be461.jpg
          # This updates the MAIN traffic records (ws, wsonline, etc.)
          
          # 1. Update 'ws' CNAME
          az network dns record-set cname update -g ${{ env.RG_NAME }} -z $zone_name -n "ws" --set CNAME="ws-${{ env.CLUSTER }}.${zone_name}" --ttl ${{ env.TTL }}
          
          # 2. Update 'wsbatch' CNAME
          az network dns record-set cname update -g ${{ env.RG_NAME }} -z $zone_name -n "wsbatch" --set CNAME="wsbatch-${{ env.CLUSTER }}.${zone_name}" --ttl ${{ env.TTL }}

          # 3. Update 'wsonline' CNAME
          az network dns record-set cname update -g ${{ env.RG_NAME }} -z $zone_name -n "wsonline" --set CNAME="wsonline-${{ env.CLUSTER }}.${zone_name}" --ttl ${{ env.TTL }}

          # 4. Update 'wsonline80' CNAME
          az network dns record-set cname update -g ${{ env.RG_NAME }} -z $zone_name -n "wsonline80" --set CNAME="wsonline80-${{ env.CLUSTER }}.${zone_name}" --ttl ${{ env.TTL }}

          # 5. Update 'wswaf' CNAME
          az network dns record-set cname update -g ${{ env.RG_NAME }} -z $zone_name -n "wswaf" --set CNAME="wswaf-${{ env.CLUSTER }}.${zone_name}" --ttl ${{ env.TTL }}

          # 6. Update 'phiauth' CNAME
          az network dns record-set cname update -g ${{ env.RG_NAME }} -z $zone_name -n "phiauth" --set CNAME="phiauth-${{ env.CLUSTER }}.${zone_name}" --ttl ${{ env.TTL }}

      - name: Send Notification
        uses: dawidd6/action-send-mail@v3
        if: always()
        with:
          # Copied structure from image_7be47a.jpg
          server_address: app-mail-eastus.us.globalegress-prod.azure.lnrsg.io
          server_port: 25
          subject: "Maintenance Failover: Switched to Cluster ${{ env.CLUSTER }}"
          body: "Automatic failover completed for ${{ env.APPLICATION }} ${{ env.LIFECYCLE }}. Traffic now pointing to Cluster ${{ env.CLUSTER }}."
          to: "your-team-email@example.com" # Update this
          from: "noreply@lexisnexisrisk.com"

________________________________________



Task 3: "What's missing?"
Here are the missing pieces:
1.	Pre-Flight Health Check:
○	Before switching DNS to the other cluster, curl the health endpoint of the target cluster. If Cluster 2 is down, the script should abort rather than sending traffic to a dead cluster.
○	Add a step before "Update DNS Records":
○	Bash
curl -f https://ws-${{ env.CLUSTER }}.us-esp-prod.azure.lnrsg.io/health || exit 1
○	
2.	Current State Awareness:
○	The script assumes Cluster 1 is Blue and Cluster 2 is Green. If you ever swap the "logical" ID of the clusters, this hardcoded cron logic might break.
3.	Intermediate Records:
○	The manual script (Image 5/6) handles "Intermediate Records" (staging/test) separately. The automated script above only moves the Main production records. Decide if you want staging to move automatically too.

