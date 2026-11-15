@description('Azure Database for MySQL Flexible Server — cheapest Burstable B1ms tier, single server hosting one logical database per service (pattern 1; documented cost tradeoff vs. one server per service). This is the one resource in this project that bills whether idle or not.')
param location string
param name string
param adminUsername string
@secure()
param adminPassword string
param databaseNames array = ['user_db', 'catalog_db', 'order_db', 'payment_db', 'inventory_db']

resource server 'Microsoft.DBforMySQL/flexibleServers@2023-12-30' = {
  name: name
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: adminUsername
    administratorLoginPassword: adminPassword
    version: '8.0.21'
    storage: {
      storageSizeGB: 20
      autoGrow: 'Disabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

resource databases 'Microsoft.DBforMySQL/flexibleServers/databases@2023-12-30' = [
  for dbName in databaseNames: {
    parent: server
    name: dbName
    properties: {
      charset: 'utf8mb4'
      collation: 'utf8mb4_general_ci'
    }
  }
]

// Allow Azure services (Container Apps) to reach the server without a fixed IP allowlist.
resource allowAzureServices 'Microsoft.DBforMySQL/flexibleServers/firewallRules@2023-12-30' = {
  parent: server
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

output fqdn string = server.properties.fullyQualifiedDomainName
output serverName string = server.name
