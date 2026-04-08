targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment')
param environmentName string

@description('Primary location for all resources')
param location string

var tags = {
  'azd-env-name': environmentName
}
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module monitoring 'monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
  }
}

output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.connectionString
