```
Title: Merge assessment-store into pre-award-stores
Owner: @srh-sloan @sfount
Collaborator(s): @samuelhwilliams @MarcUsher
Created on: 20/11/2024
Status: Approved
Finalised on: 29/11/2024
```

## Overview

The `fund-store` and `application-store` have been merged as part of an [earlier RFC](https://github.com/communitiesuk/funding-service-requests-for-comments/discussions/4).

With the larger goal of reducing the number of databases and stores we are also looking to merge `assessment-store` into this new combined stores service. This is also the next step in completing the work for this [overarching RFC](https://github.com/communitiesuk/funding-service-requests-for-comments/discussions/3) to consolidate the pre-award services into a monolith

## What is the current state?

The pre-award services have previously used 4 separate stores and databases. The work to merge them into one store is part way through, as follows:

| Name | Future Location | Status |
|--------|--------|--------|
| fund-store | pre-award-stores | Code complete, deployments in progress |
| application-store | pre-award-stores | Ready to start, once fund-store complete |
| assessment-store | pre-award-stores | Not started (this RFC) |
| account-store | TBD | Not started |

Most of these stores include some form of fund configuration, with some technical infrastructure existing between the stores themselves, and all four are talked to by both the pre-award front ends (assessment and application).


## Why should we change?

Alongside all of the challenges described in the referenced RFCs, separating the application and assessment creates two copies of the same application data, currently separated by a queue. The addition of this queue to separate application and assessment data increases complexity in the pre-award estate and adds to the number of moving parts involved in development work.

Having separate data and configuration for applications and assessments also encourages specific/ fixed mappings of data for the apply and assess process which makes the amount of configuration and work needed for onboarding challenging.

Separate data and spread out configuration can also lead to hard to track down edge cases and loses any transactional benefits of working in a standard relational database.

Merging the application store and assessment store will in time (future RFC) allow us to use a single copy of the application data, reduce the amount of configuration needed for a new fund and make the development and testing process easier and smoother.

## How should we address this?

### Phase 1

1. Lift and shift the existing `assessment-store` into `pre-award-stores`. This will follow a very similar process to combining the `fund-store` and `application-store` in that code will be kept in 2 largely separate modules initially.
    i. The application-store and assessment-store will continue to communicate via a queue, even though they are co-located.
    ii. The old assessment-store repo can be archived
    iii. Migrate the data from `assessment-store` into matching tables in `pre-award-stores`.
    iv. Update the local docker-runner setup to use pre-award-stores instead of assessment-store
5. Refine the interface for moving an application from "apply" to "assess". Instead of interfacing with SQS this will directly copy data from the "application" table to the "assessment" table in the pre-award store.
    i. At this stage the queue is no longer in use

### Phase 2
- Remove the old `assessment-store` app and database from AWS
- Remove the application import queue from AWS
- Remove the old queueing code from the `application-store` module in `pre-award-stores`
- Remove the old assessment-store service from the docker runner

### Phase 3
Establish how we can take advantage of the new merged assess and apply data to further simplify configuration and onboarding. This will be the subject of a future spike and RFC.


## What alternatives are we discarding?

 ❌ Keep things as they are - everyone has agreed that the existing architecture is too complicated and too interconnected, not giving us the benefits of true microservice architecture and being over-engineered for the scale of the services
 ❌ Consolidating the services but not merging databases - while this might simplify deployments it wouldn't address the service needs around consistent data and a significantly simpler developer experience


## Who will be affected?

At this stage it will be just the funding service developers that will be affected - they will have one less application to configure and run locally, and one less deployment.

Users should notice no tangible difference.

## Who will benefit?

Initially, just the funding service developers. But this change is a step on the road to simplifying the overall data model and configuration which will lead to shorter onboarding times, less technical complexity for the funding service teams and a more maintainable service.

## What are the key risks to manage or mitigate?

- This work depends on the previous RFCs to merge fund-store and application-store. This work is progressing well but it should be monitored to ensure it does not delay this RFC
- Migrating the data from one database to another - this process will be tested in 2 ways to mitigate risks. The overall approach will have been tested during the fund-store and application-store migrations, and the specific migration of assessment data will be tested in non-prod environments before we migrate production data. Database backups exist (and will be checked) before we do a full migration.
- As this work will involved a code freeze on the `assessment-store`, this will affect other funding service teams. Coordination will be required between platforms and live services to plan a time for this freeze to minimise disruption and conflicts.
