```
Title: Consolidate the pre-award services (stores, databases and frontends) into a monolith
Owner: Marc Usher
Collaborator(s): The Platform Team
Created on: 2024-11-08
Status: Approved
Finalised on: 2025-01-06
```

## Overview
This proposal discusses the overall goal of simplifying and consolidating the service architecture in the pre-award space into one monolith service (as far as is reasonable), and potentially merging that with the post-award monolith into one single Funding Service repository and application which still serves separate front ends for Apply, Assess, Submit and Find.

## What is the current state?
The pre-award services currently use four back-end stores and databases:

- `fund-store`
- `application-store`
- `assessment-store`
- `account-store`

It also includes two front-ends and the form runner/designer:
- `application-frontend`
- `assessment-frontend`
- `form-runner` / `form-designer` (and at some point soon the `fund-application-builder`)

It also comprises of a number of single-function services:
- `authenticator`
- `notification service`

This summary doesn't include the various queues, S3 buckets and configs that exist in between these services (see the [magical Miro](https://miro.com/app/board/uXjVLYCHRhM=/) diagram for a more complete architectural diagram).

## Why should we change?

The complexity of the pre-award architecture has been identified as a blocker to an efficient and consistent developer experience, and to the efficiency of releases and fund onboarding:
- These microservices are quite tightly coupled, with numerous places where each single Fund has to be configured, making it an awkward and error-prone manual process to add new funds and rounds.
- The fragmented databases and data stores also make it more difficult to persist one consistent data entity through the two stages of the funding lifecycle (and potentially onward after that).

The eventual aim of this consolidation work would be to move towards a more monolith-type service, which would simplify the service and fund onboarding, dev experience, deployments and data persistence significantly, and allow us to more easily meet the goals of having a consistent user experience across funding service and enable data to flow end-to-end through the service.

## How should we address this?

To minimise disruption and in order to link up this work with the Forms, Data Services and Live Services teams, we're proposing to do this through a series of steps:

1. combine the pre-award stores and databases
    1. The only possible exception to the above is `account-store`, as `account-store` and the `authenticator` service are separate but closely linked and at some point there may be ambitions to offload this to third party systems/Delta/something else, and combining this early doors might cause more work later on)
2. combine the pre-award front ends
3. combine the consolidated front ends and stores/DBs into one pre-award service
4. combine the consolidated pre-award service and post-award service

The pre-award specific stores, especially `application` and `assessment`, and the infrastructure between them are tightly coupled and should be uncontroversial for combining.

We would also merge services one at a time to minimise risk to the overall service, and each consolidation would be done in two stages:

### "Lift and shift"
- consolidate the identified combined services into one
- preserve the existing code as much as possible (schemas, names of API endpoints maintained) with any code changes focussing on making the combined services work as before
- maintaining clear separation between what will then become sub-modules (eg. hardcoded configurations brought under the same umbrella but still distinct)

### Rationalisation
- assessing the now single codebase and combined service for overlap, duplication and simplification
- refactoring the code along the above lines eg. combining endpoints that get largely the same data
- combining database tables that refer to the same data
- determining where configurations should be defined and combining these where possible to cut down on all the manual configuration changes needed

See specific RFCs for each stage of the work (this list will be updated as more RFCs are published):
- [Consolidate `fund-store` and `application-store` stores and databases
](https://github.com/communitiesuk/funding-service-requests-for-comments/discussions/4)
- [Merge assessment-store into pre-award-stores](https://github.com/communitiesuk/funding-service-requests-for-comments/discussions/8)
- [Combining pre-award frontends with `pre-award-stores`](https://github.com/communitiesuk/funding-service-requests-for-comments/discussions/13)
- [Bring `account-store` and `authenticator` into the combined pre-award monolith](https://github.com/communitiesuk/funding-service-requests-for-comments/discussions/14)

## What alternatives are we discarding?

❌  Keep things as they are - everyone has agreed that the existing architecture is too complicated and too interconnected, not giving us the benefits of true microservice architecture and being over-engineered for the scale of the services
❌  Consolidating the services but not merging databases - while this might simplify deployments it wouldn't address the service needs around consistent data and a significantly simpler developer experience

## Who will be affected?

The users should see no change at all in how the services work.

Funding Service technical teams will be the main people affected as combining the existing services will impact how they work on them.

The Live Services, Forms and Data Services teams will all be kept in the loop through timeline check-ins, RFCs and transparent sharing of key dates. Any downtime to services will be worked out in collaboration with all these teams to ensure it doesn't clash with any ongoing work.

We'll also issue RFCs at each stage of the consolidation process in order to sense-check the continuation of the work.

## Who will benefit?

In the long run, everyone! By consolidating the services in this way and reducing the complexity of the whole pre-award space (and perhaps eventually the whole funding service space) we'll reduce the number of moving parts and make it a lot easier to make, test and deploy changes to the service, debug and track requests & responses, reduce the amount of places where a Fund has to be configured and therefore quicker to onboard funds, and make it possible and simpler to persist one consistent data entity through the two stages of the funding lifecycle (and potentially onward after that).

## What are the key risks to manage or mitigate?

- Rationalising the lifted & shifted services becomes a lot more work than anticipated (especially around fund configuration/database rationalisation)
  - Mitigation - having a concurrent workstream, led by Sarah Sloan and Steven Fountain, starting with a [spike](https://mhclgdigital.atlassian.net/browse/FSPT-48) looking at what this rationalisation would mean for `assessment-store` and `application-store`
- Getting halfway through this work and team resource/priorities being changed, leaving us in a halfway state which is _more_ complicated than what we currently have
  - Mitigation - working transparently and at pace and documenting the roadmap and processes so that the work can be continued
  - Mitigation - logical but light-touch work to minimise the amount of complication and confusion from intermediary steps, such as appropriate naming of modules/services etc
 - Combining the services into a 'monolith' makes things worse
  - Mitigation - the 'old' services won't be taken offline until we're sure the new simplified architecture and combined services work properly, are robust and meet the needs they set out to meet
