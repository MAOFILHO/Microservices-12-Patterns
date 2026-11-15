@description('''
Deploys the whole stack: ACR (Basic), Container Apps Environment (Consumption), MySQL Flexible
Server (Burstable B1ms, one logical DB per service), a Static Web App (Free) for the React
frontend, and one Container App per service (user, catalog, order, payment, inventory) plus
the API gateway.
Every SKU is the cheapest tier that meets the need. Names are resolved by infra/provision.py
BEFORE this deployment runs, after checking for collisions.
''')
param location string = resourceGroup().location

param acrName string
param logAnalyticsName string
param containerAppsEnvName string
param staticWebAppName string
param mysqlServerName string

@description('Azure Static Web Apps is only available in a handful of regions (Central US, East US 2, West US 2, West Europe, East Asia) — NOT every region that supports Container Apps/MySQL/etc. (e.g. plain "East US" does not support it). Kept as its own parameter, independently configurable via AZURE_STATIC_WEB_APP_LOCATION in .env, so the primary `location` can be whatever region the user wants without breaking this one resource.')
param staticWebAppLocation string = 'eastus2'

param mysqlAdminUsername string
@secure()
param mysqlAdminPassword string

@description('Image tag to deploy for every service — set by provision.py after az acr build pushes images.')
param imageTag string = 'latest'

@description('Set true only when Container Apps should be created with minReplicas=1 for a live demo. Default false = scale-to-zero, effectively $0 idle cost.')
param keepWarm bool = false

var minReplicas = keepWarm ? 1 : 0

module logAnalytics 'modules/log-analytics.bicep' = {
  name: 'logAnalytics'
  params: {
    location: location
    name: logAnalyticsName
  }
}

module acr 'modules/acr.bicep' = {
  name: 'acr'
  params: {
    location: location
    name: acrName
  }
}

module containerAppsEnv 'modules/container-apps-env.bicep' = {
  name: 'containerAppsEnv'
  params: {
    location: location
    name: containerAppsEnvName
    logAnalyticsCustomerId: logAnalytics.outputs.customerId
    logAnalyticsSharedKey: logAnalytics.outputs.sharedKey
  }
}

module mysql 'modules/mysql.bicep' = {
  name: 'mysql'
  params: {
    location: location
    name: mysqlServerName
    adminUsername: mysqlAdminUsername
    adminPassword: mysqlAdminPassword
  }
}

module staticWebApp 'modules/static-web-app.bicep' = {
  name: 'staticWebApp'
  params: {
    location: staticWebAppLocation
    name: staticWebAppName
  }
}

var commonEnv = [
  { name: 'RUN_MODE', value: 'azure' }
  { name: 'AZURE_MYSQL_HOST', value: mysql.outputs.fqdn }
  { name: 'AZURE_MYSQL_PORT', value: '3306' }
  { name: 'AZURE_MYSQL_ADMIN_USER', value: mysqlAdminUsername }
  { name: 'AZURE_MYSQL_ADMIN_PASSWORD', secretRef: 'mysql-password' }
]

var acrPassword = listCredentials(resourceId('Microsoft.ContainerRegistry/registries', acrName), '2023-11-01-preview').passwords[0].value

module user 'modules/container-app.bicep' = {
  name: 'user'
  params: {
    location: location
    name: 'user'
    environmentId: containerAppsEnv.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.registryName
    acrPassword: acrPassword
    mysqlAdminPassword: mysqlAdminPassword
    imageName: 'user'
    imageTag: imageTag
    targetPort: 5101
    minReplicas: minReplicas
    envVars: commonEnv
  }
}

module catalog 'modules/container-app.bicep' = {
  name: 'catalog'
  params: {
    location: location
    name: 'catalog'
    environmentId: containerAppsEnv.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.registryName
    acrPassword: acrPassword
    mysqlAdminPassword: mysqlAdminPassword
    imageName: 'catalog'
    imageTag: imageTag
    targetPort: 5102
    minReplicas: minReplicas
    envVars: commonEnv
  }
}

module order 'modules/container-app.bicep' = {
  name: 'order'
  params: {
    location: location
    name: 'order'
    environmentId: containerAppsEnv.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.registryName
    acrPassword: acrPassword
    mysqlAdminPassword: mysqlAdminPassword
    imageName: 'order'
    imageTag: imageTag
    targetPort: 5103
    minReplicas: minReplicas
    // In Azure, Container Apps DNS does service discovery (pattern 12): no REGISTRY_URL here.
    envVars: concat(commonEnv, [
      { name: 'USER_SERVICE_BASE_URL', value: 'https://${user.outputs.fqdn}' }
      { name: 'CATALOG_SERVICE_BASE_URL', value: 'https://${catalog.outputs.fqdn}' }
      { name: 'PAYMENT_SERVICE_BASE_URL', value: 'https://${payment.outputs.fqdn}' }
    ])
  }
}

module payment 'modules/container-app.bicep' = {
  name: 'payment'
  params: {
    location: location
    name: 'payment'
    environmentId: containerAppsEnv.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.registryName
    acrPassword: acrPassword
    mysqlAdminPassword: mysqlAdminPassword
    imageName: 'payment'
    imageTag: imageTag
    targetPort: 5104
    minReplicas: minReplicas
    envVars: commonEnv
  }
}

module inventory 'modules/container-app.bicep' = {
  name: 'inventory'
  params: {
    location: location
    name: 'inventory'
    environmentId: containerAppsEnv.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.registryName
    acrPassword: acrPassword
    mysqlAdminPassword: mysqlAdminPassword
    imageName: 'inventory'
    imageTag: imageTag
    targetPort: 5105
    minReplicas: minReplicas
    envVars: commonEnv
  }
}

module gateway 'modules/container-app.bicep' = {
  name: 'gateway'
  params: {
    location: location
    name: 'gateway'
    environmentId: containerAppsEnv.outputs.environmentId
    acrLoginServer: acr.outputs.loginServer
    acrUsername: acr.outputs.registryName
    acrPassword: acrPassword
    mysqlAdminPassword: mysqlAdminPassword
    imageName: 'gateway'
    imageTag: imageTag
    targetPort: 8100
    minReplicas: minReplicas
    envVars: [
      { name: 'RUN_MODE', value: 'azure' }
      { name: 'USER_SERVICE_BASE_URL', value: 'https://${user.outputs.fqdn}' }
      { name: 'CATALOG_SERVICE_BASE_URL', value: 'https://${catalog.outputs.fqdn}' }
      { name: 'ORDER_SERVICE_BASE_URL', value: 'https://${order.outputs.fqdn}' }
      { name: 'PAYMENT_SERVICE_BASE_URL', value: 'https://${payment.outputs.fqdn}' }
      { name: 'INVENTORY_SERVICE_BASE_URL', value: 'https://${inventory.outputs.fqdn}' }
      { name: 'FRONTEND_ORIGIN', value: 'https://${staticWebApp.outputs.defaultHostname}' }
    ]
  }
}

output acrLoginServer string = acr.outputs.loginServer
output acrName string = acr.outputs.registryName
output mysqlFqdn string = mysql.outputs.fqdn
output containerAppsEnvId string = containerAppsEnv.outputs.environmentId
output containerAppsDefaultDomain string = containerAppsEnv.outputs.defaultDomain
output staticWebAppHostname string = staticWebApp.outputs.defaultHostname
output gatewayFqdn string = gateway.outputs.fqdn
