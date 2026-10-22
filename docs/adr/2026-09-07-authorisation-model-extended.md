```
Title: Authorisation model update
Owner: Marc Usher
Collaborator(s): Platform Team
Created on: 2026-08-25
Status: Final
Finalised on: 2026-09-07
```

## Overview
This is an update to the previously-written [ADR on authorisation](https://github.com/communitiesuk/funding-service-requests-for-comments/blob/main/adr/2025-05-28-authorisation-model.md). It was written as we started to build out the permissions model and included some best guesses for how roles and permissions would work, but as Deliver and Access grant funding have developed and onboarded multiple grants, grant policy teams and grant recipient users, there have been enough changes to that original intention and outline to warrant an update on how we (currently) model role-based access control in our service.

## What changed from the initial plan?
The approach outlined in the original ADR, linking Users, Grants and Organisations via a `UserRole` table with nullable columns helping define role levels and permissions (via a set role enum), is still the approach we have taken. Where things have diverged is in:

- **Number of roles in a row/per level** - the original ADR implied that each level of permission (ie. platform level, org level or grant level) would only include one specific role, and uniqueness enforced at the user/org/grant level would only allow one role per level. We now allow multiple roles per level (eg. a user could be a `certifier` and `data-provider` for a specific grant, and all rows include `member` as a default minimum)
- **Roles enum** - we have expanded the role enum ([defined below](#Roles)) in order to accommodate a user need for access to certain parts of the admin panel without being granted full admin access, roles and permission levels which we hadn’t previously anticipated.
- **Authorisation helper** - we have now implemented the permissions-checking core library mentioned in the ADR, an `AuthorisationHelper` library which also integrates with our route decorators. [Further explanation below](#Authorisation-helper).
- **Deliver users testing as Access users** - as the service has developed, there was a strong user need for internal Deliver users to be able to test the grant recipient journey on Access grant funding, for UAT of forms, quality control, support and testing branching. This has led to an extension of how we model organisations and internal users being able to have Access grant funding specific permissions for specific `test` organisations. [Further explanation below](#Organisations-and-testing).

### Roles

| Role name | Description |
| -------- | ------- |
| `admin` | Given the highest level of access for the granularity at which it’s added (platform level, organisation level or grant level) |
| `data-analyst` | Deliver grant funding specific role, to be able to see the Data analysis tab in the admin panel |
| `grant-lifecycle-manager` | Deliver grant funding specific role, to be able to see and use the Collection lifecycle tab in the admin panel |
| `data-provider` | Access grant funding specific role, to be able to complete and submit (but not certify) collections |
| `certifier` | Access grant funding specific role, to be able to view and certify (but not edit) collections |
| `member` | Read-only level access for the granularity at which it’s added. All rows in the UserRole table get member automatically added. |

### Permissions model

#### Admin roles (i.e. not tied to an organisation or grant)

| Role type | Description | Database row |
| -------- | ------- | ------- |
| Funding Service platform admin | Full platform admin privileges | `admin` role <br> no `organisation_id` <br> no `grant_id` |
| Funding Service data analyst | Able to see the Data analysis tab in the admin panel | `data-analyst` role <br> no `organisation_id` <br> no `grant_id` |
| Funding Service grant lifecycle manager | Able to see and use the Collection lifecycle tab in the admin panel as well as key tabs for managing user permissions, resolving support requests and general service management (currently Invitations, Submissions, Delta certifiers and Release notes) | `grant-lifecycle-manager` role <br> no `organisation_id` <br> no `grant_id` |

#### Deliver grant funding roles

| Role type | Description | Database row |
| -------- | ------- | ------- |
| MHCLG Organisation admin | An internal user who needs full overview of all MHCLG grants and can create and edit grants and create and edit collections for any MHCLG-owned grant (predominantly the permission level given to form designers) | `admin` role <br> MHCLG grant-owning org `organisation_id` <br> no `grant_id` |
| MHCLG Organisation member | An internal user who needs full overview of all MHCLG grants and can create and edit grants and create and edit collections for any MHCLG-owned grant they created (predominantly the permission level given to other Funding Service users) | `member` role <br> MHCLG grant-owning org `organisation_id` <br> no `grant_id` |
| MHCLG Grant team member | An internal Grant Team user with read-only access to a specific grant | `member` role <br> MHCLG grant-owning org `organisation_id` <br> Specific `grant_id` |


#### Access grant funding roles

| Role type | Description | Database row |
| -------- | ------- | ------- |
| Grant recipient organisation certifier | A grant recipient organisation certifier (eg. S151 Officer) who should see all pre and post award collections for their organisation and be able to certify and submit those that need certification | `certifier` role <br> Grant recipient org `organisation_id` <br> no `grant_id` |
| Grant recipient organisation certifier override | A grant recipient organisation certifier (eg. Deputy S151 Officer) who can certify and submit a specific collection | `certifier` role <br> Grant recipient org `organisation_id` <br> Specific `grant_id` |
| Grant recipient organisation data provider | A grant recipient organisation user who can edit and submit specific collections (for certification or to MHCLG for non-certified collections) | `data-provider` role <br> Grant recipient org `organisation_id` <br> Specific `grant_id` |


### Authorisation helper

The original ADR mentioned a need to implement a permissions-checking core library. This was built out and lives as the `AuthorisationHelper`.

This helper class has a number of methods which can consistently be called in the codebase, including in page templates, to gate certain actions and functionality to specific permission levels and roles, eg. only certifiers being able to submit a collection that needs certification, or only platform-level admins being able to see most of the admin panel tabs. It also enforces the role hierarchy, ie. that platform admins can see and do most things, that MHCLG admins can do more than members, but if something is gated at MHCLG member level then those actions are also accessible to MHCLG and platform admins.

The methods have been named to be as explicit as possible and reduce confusion as to the role/permission level to make the code readable and any gating clear.

The AuthorisationHelper methods are also pulled into our route decorators, allowing us to safeguard entire journeys and views from users who do not have the correct permission levels, with decorators also wrapping other decorators to enforce permission hierarchies.

This functionality is all enforced through testing - all new routes are expected to have an integration test ensuring the permission levels match what’s expected, and we have a global test which ensures every new route is gated with a permissions decorator powered by the `AuthorisationHelper`.

### Organisations and testing

Our Organisation model has grown slightly, but the biggest change (and how this relates to authorisation) is around the testing journey.

As the service has grown there was a strong user need for internal Deliver users to be able to test the grant recipient journey on Access grant funding, rather than just the basic form preview. This was needed so grant policy teams could get an idea of what grant recipient users would see, including email comms throughout the journey, as well as for UAT and quality control of forms and resolving support requests.

Another use for this emerged with the work around data sets - being able to test as specific grant recipient organisations in order to test conditional branching or validation based on data set values, which is what drove the decision below to have `live` and `test` organisations.

#### Test grant recipients and test organisations

Non-grant owning organisations (ie. grant recipient organisations) now exist in one of two modes - `live` (for real orgs and real users) and `test` (for Deliver users testing in access). The Organisation entities in the database are identical except for having their own unique ID, `(test)` appended to the organisation name of the test org, and the difference in mode. Importantly their `external_id` is identical, as this `external_id` lookup is what powers data set values being pulled into our expression context for interpolation and evaluation against the stored values.

When a new `live` organisation is created via the reporting lifecycle, a `test` organisation is also created.

The GrantRecipient model also has a similar `live`/`test` split, and when a new `live` grant recipient row is created via the reporting lifecycle, a `test` grant recipient row is also created.

Internal Deliver grant funding users are therefore able to have `data-provider` and `certifier` roles for the `test` organisations without worrying about impacting or overlapping with real Access grant funding users. They are able to test the full lifecycle and collection completion and submission, including lifecycle emails, safely, and without notifying real users or affecting real data.

A Deliver grant funding user might therefore end up with these kinds of rows associated with them in the database:

| User | Organisation | Grant | Roles |
| -------- | ------- | ------- | ------- |
| John Cheese | `null` | `null` | `data-analyst` <br> `grant-lifecycle-manager` <br> `member` |
| John Cheese | MHCLG | `null` | `admin` <br> `member` |
| John Cheese | Swansea Council (test) | Cheeseboards in Parks | `certifier` <br> `data-provider` <br> `member` |
| John Cheese | Camden London Borough (test) | Frog Safety Fund | `certifier` <br> `data-provider` <br> `member` |


Grant team members (ie. Deliver grant funding users who are member of a specific grant for read-only access) are automatically given `data-provider` and `certifier` permissions for all test grant recipients associated with their grant, so they can automatically do the full grant recipient journey testing.

Currently, other internal users (eg. form designers, grant relationship managers) have to be manually granted testing permission, but there is a [ticket to address this](https://mhclgdigital.atlassian.net/browse/FSPT-1533).

## How might things change going forward?

### Competed pre-award journey

At the time of writing, a competed pre-award journey and flow is being designed and built out to support competitive grant applications with eligibility questions. In this flow, we won’t know on behalf of which organisation the users are applying for grant funding until partway through the flow.

The symmetry between `live`/`test` organisations is expected to be relaxed here, as there are a number of usability and security concerns which would make this inadvisable (eg. grant teams knowing which organisations are submitting applications by virtue of a `test` grant recipient organisation appearing before the application is ready and presentable). In order to test this flow, the Deliver grant funding user may also set up a new organisation. It’s not expected that this would immediately create a related `live` organisation.

More on these changes will be written up separately as the work progresses.

### Other government departments

When other government departments or grant-owning organisations are onboarded, there will be some questions and threads to pull around visibility of grants and functionality, such as:

- Should users of one grant-owning organisation be able to see grants from other grant-owning organisations?
- Should platform admins be able to see info and data for all grants, regardless of which organisation owns it?

### New roles

New roles will likely be added to the `RoleEnum` over time, and these will need to be factored into the existing role hierarchy and modelled appropriately.

As with the existing roles, check constraints should be added as needed to enforce the set of permission combinations the business logic supports.

## What are the key risks to manage or mitigate?

- Role hierarchy is not centrally declared - each method in the `AuthorisationHelper` codifies the role hierarchy independently, rather than deriving from a single ordered hierarchy definition (whether defining this hierarchy explicitly is helpful is another question as there are instances where this hierarchy needs to be explicitly circumvented eg. only grant team members are able to reopen a submission, not even platform admins are able to do this). This works for now but is a risk as the service grows and new roles are modelled and added. This also runs the risk of losing a clear picture of our permissions model, and it will be important to maintain clear documentation (or make sure the `AuthorisationHelper` is clear enough to be self documenting) so it’s clear which roles can do what.
- `member` role redundancy - we currently add the `member` role along with any other roles a user needs, but there are only a couple specific permissions (Deliver grant funding MHCLG member or grant team member at a per-grant level) where this actually means anything. For all other roles it’s redundant, and has been kept as a fallback if we ever need a read-only permission. Any future removal of `member` permissions will need coordinated thinking and changes, as it’s built in to a number of baseline authorisation checks.
- Deliver users testing access - the need for this is sound and the scope of what users can test continues to grow, but most of it relies on a single `AuthorisationHelper` method and we should continue to make sure this works as expected, as the consequences of bugs here would be severe (potentially affecting live Access and Deliver grant funding users, though this is mitigated by the fact that Deliver user permissions for testing are tied to `test` organisations).
- `live`/`test` symmetry diverging - [mentioned above](#Competed-pre-award-journey) but this divergence will need to be well documented to ensure the entire team (all disciplines) understand the nuance of the `test` grant recipient journey in the different stages of the funding lifecycle and how it works in the service. The assumption of mirrored `live` and `test` organisations is also baked into a number of places (eg. automatic test permissions for Deliver grant funding users, submission mode checking). The identical `external_id` powers data sets, so changes to this should be well scoped and thought through, with checks against regressions.
