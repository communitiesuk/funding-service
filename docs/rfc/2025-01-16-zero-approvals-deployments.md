    Title: Move towards no-manual-intervention continuous deployment
    Owner: Samuel Williams
    Collaborator(s): The Platform Team
    Created on: 07/01/2025
    Status: In progress
    Finalised on: 2025-01-16

## Overview

At the moment, deploying an app (eg `pre-award`) to production requires three manual approval steps: UAT deploy, UAT tests, and prod deploy.

This RFC is focused on removing these manual approval steps so that, once a change has been merged to the main branch, it deploys to each environment automatically. If automated tests in that environment pass, it will automatically be promoted to the next environment until production is reached.

This RFC has some interplay with https://github.com/communitiesuk/funding-service-requests-for-comments/discussions/17, which discusses removing the UAT environment altogether. However, I think this stands alone enough to still be decided independently.

## What is the current state?

Here is a deployment run for the `pre-award` service:
<img width="2575" alt="image" src="https://github.com/user-attachments/assets/4a6a4c05-a5a2-447e-b8df-9181eddd70cb" />

The final three columns each require a manual approve/reject action by a developer before they are run.

## Why should we change?

With more developers merging PRs to a single repo, manual approvals mean that each developer has to 'babysit' their merged PRs over ~30+ minutes in order to get them into production. This is either fully lost time, or causes a significant amount of context switching, which can decrease productivity and increase the chance of making mistakes in whatever they're working on.

Alternatively, if the developer forgets to manually approve their pipeline and get it into production, then any other developers merging PRs later now need to gain confidence that these as-yet-unreleased changes are ready to go into production.

If a stack of changes end up having an error, it's harder to identify what caused that specific error, leading to confusion and more delays in releasing to production.

Many developers on the team are not currently doing manual testing of their changes in the `test`/`uat` environments, and instead just waiting to press the approve+deploy buttons for `uat` and `prod`. If no manual action is taken in the pre-prod environments, having a manual approval step is providing little actual benefit.

## How should we address this?

The proposal here is to remove the manual approval steps required in the github actions pipeline for each of the following steps: UAT deploy, UAT tests, prod deploy. As soon as a pipeline is started (eg when merging a PR), it will automatically deploy to the `test` environment and run tests. If they pass, it will repeat with the `UAT` environment. If those tests pass, it will automatically deploy to `production`. This removes the need for developers to oversee the deployment of their code after pressing 'Merge' on a PR.

I further propose we implement a more robust and simpler feature flags system, with some manner of direct configuration like a web UI. This will require knowledge-sharing and upskilling the wider tech team on how to make good use of these flags. This would allow PRs to be merged that enable a feature, without actually turning it on in all environments or necessarily being 100% complete (ie enabling smaller incremental PRs to deliver the feature).

We should implement this RFC in stages:

1. Remove the manual approvals from UAT immediately.
2. Do preparatory work to take us to an appropriate level of confidence to remove the approvals from the production deployment step. This might include:
    * Improvements to our e2e test coverage.
    * Improvements to our deployment pipeline to allow more fine-grained control (eg suspending/cancelling/pinning deployments)
    * Implementing feature flagging
    * SlackOps of some kind
    * etc
3. Remove approvals from prod deploy.

## What alternatives are we discarding?

- The existing process, where manual approval is required for each of: UAT deploy, UAT tests, prod deploy.
- A compromise between both, where manual approval is required for just the prod deploy.

## Who will be affected?

- Developers
- Product Managers and QA. Because changes will be deployed straight through to production with no manual approvals step, processes around product sign-off and QA will need to change. There are options for how:
  1. These review steps could happen before the code is merged, either by a synchronous developer walk-through, or by deploying the changes to the `dev` environment and letting the PM/QA do their work there. The latter needs some agreement/collaboration between developers, as we currently only have a single dev environment.
  4. We can make more use of feature flags to disable/'hide' work-in-progress so that it isn't visible to users in production before everything is complete and/or signed-off. Product sign-off could result in "enabling the feature flag in production". This would let `test` or `uat` still be used for sign-off/review (where the feature is enabled), but without blocking deployment to production (where the feature is disabled).
- QA will need to adapt to testing in a different way - either by running services locally, using the `dev` environment pre-merge, or working with feature flags.

## Who will benefit?

- Developers will benefit from not having to 'babysit' pipelines in order to get their changes to production. They also won't need to check whether there are other staged changes that haven't been released yet and gain confidence that these are OK to release.
- If feature flags: product managers will have more control over the release of new features, and broken features will be able to be disabled/rolled back more easily and more quickly.

## What are the key risks to manage or mitigate?

- With the current state where developers should own their merged pipeline and make sure it gets to production, that developer is likely to notice errors or failures in the deployment. With zero-approval continuous deployment, we need to make sure that failed deployments are easily visible and the associated developer owns fixing that problem so that others on the team are not blocked.
- Inability to prevent a merged change getting to production if a developer identifies or realises there is a problem.
  - We could add an artificial delay/pause between tests finishing in the env before prod, and the deploy to prod, which would allow the pipeline run to be cancelled in an emergency.
