@description('One reusable Container App module — instantiated once per service from main.bicep (user, catalog, order, payment, inventory, gateway, redis). Explicit cheap defaults: Consumption plan, minReplicas 0 (scale-to-zero), 0.25 vCPU / 0.5Gi.')
param location string
param name string
param environmentId string
param acrLoginServer string
param acrUsername string
@secure()
param acrPassword string
param imageName string
param imageTag string
param targetPort int
@description('Explicit minReplicas — never left to an implicit default. 0 = scale-to-zero, no idle billing.')
param minReplicas int = 0
param maxReplicas int = 3
param cpu string = '0.25'
param memory string = '0.5Gi'
param envVars array = []
param external bool = true
@description('auto = HTTP(S). tcp for non-HTTP backends such as Redis; internal TCP needs no custom VNet.')
param transport string = 'auto'
@description('TCP only: the port other apps in the environment connect to. 0 = not set (HTTP apps).')
param exposedPort int = 0
@description('Extra secrets for this app only, e.g. the user service signing key: [{ name, value }].')
@secure()
param extraSecrets object = {}
@description('Secret value for the AZURE_MYSQL_ADMIN_PASSWORD env var, referenced via secretRef so it never appears in plain env vars or deployment output. Empty for apps without a database (Redis), which then get no MySQL secret at all.')
@secure()
param mysqlAdminPassword string = ''
@description('Grants a system-assigned managed identity. Off for every app today; kept for later milestones.')
param enableSystemIdentity bool = false

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  identity: enableSystemIdentity ? {
    type: 'SystemAssigned'
  } : null
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      ingress: {
        external: external
        targetPort: targetPort
        transport: transport
        exposedPort: exposedPort == 0 ? null : exposedPort
      }
      registries: [
        {
          server: acrLoginServer
          username: acrUsername
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: concat([
        {
          name: 'acr-password'
          value: acrPassword
        }
      ], empty(mysqlAdminPassword) ? [] : [
        {
          name: 'mysql-password'
          value: mysqlAdminPassword
        }
      ], extraSecrets.?items ?? [])
    }
    template: {
      containers: [
        {
          name: name
          image: '${acrLoginServer}/${imageName}:${imageTag}'
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: envVars
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output fqdn string = containerApp.properties.configuration.ingress.fqdn
output name string = containerApp.name
output principalId string = enableSystemIdentity ? containerApp.identity.principalId : ''
