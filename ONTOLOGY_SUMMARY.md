# CADO ontology summary

22 classes, 27 object properties, 21 data properties.

### CADO classes

| Class | Subclass of | Equivalent to | Restrictions |
|---|---|---|---|
| container_orchestration_environment | owl:Thing | - | - |
| deployment_unit | container_orchestration_environment | - | runningInstanceOf only image; binds only storage; hostedBy only host; hasEnvironmentVariable only environment_variable; hasVolumeMount only volume_mount; containsMinimalDeploymentUnit only minimal_deployment_unit; dependsOn only deployment_unit |
| environment_variable | container_orchestration_environment | - | variable_name exactly 1 Thing; variable_value exactly 1 Thing |
| ephemeral | storage | - | - |
| group_by | container_orchestration_environment | - | includesRunningInstance only deployment_unit |
| host | container_orchestration_environment | - | - |
| image | container_orchestration_environment | - | savedTo only host |
| image_registry | container_orchestration_environment | - | includesImage only image |
| minimal_deployment_unit | deployment_unit | - | runningInstanceOf exactly 1 image |
| namespace | group_by | - | - |
| network | group_by | - | - |
| persistent | storage | - | reservesDiskSpaceOn min 1 host |
| platform | container_orchestration_environment | - | composedOf only container_orchestration_environment; deploys only deployment_unit; includesHost only host; generatesGroupBy only group_by; generatesSecret only secret; generatesStorage only storage; pullsImageFrom only image_registry |
| private_image_registry | image_registry | - | - |
| public_image_registry | image_registry | - | - |
| runtime_environment | container_orchestration_environment | - | convertsToContainer only image; unpacks only image; pullsImageFrom only image_registry |
| secret | container_orchestration_environment | - | loginTo only private_image_registry |
| service | group_by | - | - |
| stateful_deployment_unit | deployment_unit | deployment_unit and hasVolumeMount some mountsStorage some persistent | - |
| storage | container_orchestration_environment | - | reservesDiskSpaceOn only host |
| subplatform | platform | platform and utilizedBy some platform | - |
| volume_mount | container_orchestration_environment | - | mountsStorage only storage; mountsStorage exactly 1 storage; mount_path exactly 1 Thing |

### CADO object properties

| Object property | Domain | Range | Characteristics |
|---|---|---|---|
| binds | deployment_unit | storage | - |
| composedOf | platform | container_orchestration_environment | asymmetric, irreflexive |
| containsMinimalDeploymentUnit | deployment_unit | minimal_deployment_unit | asymmetric, irreflexive |
| convertsToContainer | runtime_environment | image | - |
| dependsOn | deployment_unit | deployment_unit | asymmetric, irreflexive |
| deployedBy | deployment_unit | platform | inverse of deploys |
| deploys | platform | deployment_unit | inverse of deployedBy |
| generatesGroupBy | platform | group_by | - |
| generatesSecret | platform | secret | - |
| generatesStorage | platform | storage | - |
| groupedBy | deployment_unit | group_by | inverse of includesRunningInstance |
| hasEnvironmentVariable | deployment_unit | environment_variable | - |
| hasVolumeMount | deployment_unit | volume_mount | - |
| hostedBy | deployment_unit | host | inverse of hosts |
| hosts | host | deployment_unit | inverse of hostedBy |
| includesHost | platform | host | - |
| includesImage | image_registry | image | - |
| includesRunningInstance | group_by | deployment_unit | inverse of groupedBy |
| loginTo | secret | private_image_registry | - |
| mountsStorage | volume_mount | storage | - |
| pullsImageFrom | platform or runtime_environment | image_registry | - |
| reservesDiskSpaceOn | storage | host | - |
| runningInstanceOf | deployment_unit | image | - |
| savedTo | image | host | - |
| unpacks | runtime_environment | image | - |
| utilizedBy | platform or runtime_environment | platform or runtime_environment | inverse of utilizes |
| utilizes | platform or runtime_environment | platform or runtime_environment | asymmetric, irreflexive, inverse of utilizedBy |

### CADO data properties

| Data property | Domain | Range | Characteristics |
|---|---|---|---|
| artifact_format | platform | xsd:str | functional |
| container_name | deployment_unit | xsd:str | functional |
| cpu_limit | deployment_unit | xsd:str | functional |
| deployment_name | deployment_unit | xsd:str | functional |
| driver | storage | xsd:str | functional |
| image_name | image | xsd:str | functional |
| memory_limit | deployment_unit | xsd:str | functional |
| mount_path | volume_mount | xsd:str | functional |
| namespace_name | namespace | xsd:str | functional |
| network_name | network | xsd:str | functional |
| ports | deployment_unit | xsd:str | - |
| registry_url | image_registry | xsd:normstr | functional |
| replicas | deployment_unit | xsd:int | functional |
| reserved_storage | storage | xsd:str | functional |
| restart_policy | deployment_unit | xsd:str | functional |
| service_name | service | xsd:str | functional |
| variable_name | environment_variable | xsd:str | functional |
| variable_value | environment_variable | xsd:str | functional |
| version | platform | xsd:str | functional |
| volume_host_path | persistent | xsd:str | functional |
| volume_name | storage | xsd:str | functional |
