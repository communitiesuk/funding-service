```
Title: Consolidate `fund-store` and `application-store` stores and databases
Owner: marc.usher@communities.gov.uk
Collaborator(s):
Created on: 2024-11-07
Status: Accepted
Finalised on: 2024-11-21
```

## Overview
This proposal discusses merging the `fund-store` and `application-store` stores (ie. back-end API services) and databases. This is the first in a series of proposed steps to simplify and consolidate the service architecture in the pre-award space (see the [RFC on moving to a monolith](https://github.com/communitiesuk/funding-service-requests-for-comments/discussions/3) for more details).

## What is the current state?
The pre-award services currently use four back-end stores and databases:

- `fund-store`
- `application-store`
- `assessment-store`
- `account-store`

Most of these stores include some form of fund configuration, with some technical infrastructure existing between the stores themselves, and all four are talked to by both the pre-award front ends (`assessment` and `application`).

## Why should we change?

This would be the first step in the Platform team simplifying and consolidating the pre-award architecture.

We identified the back-end stores and databases as having a fairly small-ish scope, without massive technical barriers, while still improving the overall situation (eg for teams such as Live Services).

The `fund-store` and `application-store` are the easiest of the stores to merge first as the `fund-store` is relatively separate and distinct from both `application-store` and `assessment-store`, and the tables in these databases refer to each other but there's no domain overlap.

Starting with these stores and databases allows us to gain confidence in our process, deliver something quickly, and prove a blueprint for how the rest of the consolidation work will go.

## How should we address this?

To minimise disruption and in order to link up with the Forms, Data Services and Live Services teams, we're proposing to do this through a series of steps:
- "lift and shift" the `fund-store` into a new combined back-end service called `pre-award-stores`
- migrate the local set-up and deployed environments to use the new `pre-award-stores` back-end service
- "lift and shift" the `application-store` into `pre-award-stores` and combine it with the previously moved `fund-store`

We've already done a short spike to test the feasibility of this approach ([see more info on the Spike](https://mhclgdigital.atlassian.net/browse/FSPT-53) and the steps taken to combine these two services as a test)

We've also produced a [draft migration plan](https://mhclgdigital.atlassian.net/wiki/spaces/FS/pages/330170536/Migration+plan+for+funding-service-pre-award-stores) detailing the proposed steps to deploy the combined services to the various environments and to do the data migrations.

See the [overall epic for this work on Jira](https://mhclgdigital.atlassian.net/browse/FSPT-50), broken down into the stories to cover the steps outlined above.

## What alternatives are we discarding?

❌  Keep things as they are - everyone has agreed that the existing architecture is too complicated and too interconnected, not giving us the benefits of true microservice architecture and being over-engineered for the scale of the services
❌  Consolidating the services but not merging databases - while this might simplify deployments it wouldn't address the service needs around consistent data and a significantly simpler developer experience

## Who will be affected?

The users should see no change at all in how the services work.

Funding Service technical teams will be the main people affected as combining the existing services will impact how they work on them. This change will likely most affect the Live Services team, but all teams will be kept in the loop through timeline check-ins, RFCs and transparent sharing of key dates. Any downtime to services will be worked out in collaboration with all these teams to ensure it doesn't clash with any ongoing work.

## What are the key risks to manage or mitigate?

- Rationalising the lifted & shifted services becomes a lot more work than anticipated (especially around fund configuration/database rationalisation)
  - *Mitigation* - having a concurrent workstream, led by Sarah Sloan and Steven Fountain, starting with a [spike](https://mhclgdigital.atlassian.net/browse/FSPT-48) looking at what this rationalisation would mean for `assessment-store` and `application-store`
- Unanticipated complications or delays with the migration
  - *Mitigation* - the  [draft migration plan](https://mhclgdigital.atlassian.net/wiki/spaces/FS/pages/330170536/Migration+plan+for+funding-service-pre-award-stores) will be workshopped and shared widely across the teams for visibility and comment, and any IT involvement will be scheduled ahead of time to ensure we meet their timelines for any change requests
