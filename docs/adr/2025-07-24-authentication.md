```
Title: Authentication for MVP
Owner: Marc Usher
Collaborator(s): Platform Team
Created on: 2025-08-15
Status: Final
Finalised on: 2025-08-15
```

## Overview
The new Funding Service platform is conceptually split into two services — Deliver Grant Funding, for grant team members and Funding Service admin users, and Access Grant Funding, for grant applicants and recipients.

The service will have a number of users, including Funding Service admins, grant teams, other government department (OGD) teams, assessors, grant applicants, grant recipients and Section 151 Officers. Our authentication methods need to be secure, robust and reliable, meeting service standards, secure by design principles and MHCLG Cyber Security requirements, while also meeting the user needs for these internal and external user groups.

This ADR touches on briefly how, in the current service, authentication is closely tied with authorisation, but you can [read the recent authorisation ADR](https://github.com/communitiesuk/funding-service-requests-for-comments/blob/main/adr/2025-05028-authorisation-model.md) for more on Deliver/Access Grant Funding's proposed authorisation model.

## What is the current state?

Authentication on our current services (Apply, Assess, Find, Submit) is currently a mix of two authentication methods: magic links, and federated authentication via Microsoft Azure AD using MHCLG's Azure AD tenant. All authentication is handled by what was previously a separate Funding Service-built microservice, 'Authenticator', which is now part of the consolidated 'Pre-award' codebase.

### Apply
Applicants are sent direct links to grant application pages and on visiting those pages are prompted to input their email to generate 'magic links'. They receive an email with a link which allows them to authenticate and access a session to start or complete the application process. Due to the permissions model for Apply, all applications are therefore tied to just one user and cannot be shared or collaborated on by users in the same organisation.

### Assess
Authentication to the Assess service requires users to have an @communities.gov.uk email address or be guest users in MHCLG's Azure AD tenant. These users are manually added to Azure AD Security Groups relating to the grant they will be assessing and their relevant permission level (eg. Lead Assessor), and these Azure AD Security Groups are used to determine their role and permission level within Apply.

![Assess Authentication Architecture Diagram](https://github.com/user-attachments/assets/66feccb8-7bb5-44ad-922b-7b979396c4e6)

![Assess Permission Groups](https://github.com/user-attachments/assets/55a00cba-5b70-4d83-b1c5-5e7bdac54fcc)

### Find Monitoring Data
Find is available to anyone with a @communities.gov.uk email through federated authentication via Azure AD.

### Submit Monitoring Data
Submit requires users to be within MHCLG's Azure AD tenant and also added to specific Azure AD Security Groups for the relevant grant, which then assigns their user a Role which allows them to access the application. For the vast majority of users, who are from Local Authorities or consultancies working with Local Authorities to deliver or manage funded projects and programmes, this means manually adding them as guest users in the system.

Based on their email domain we map them to a Local Authority and determine who they are able to submit returns for. There are a number of users who need to be able to submit for multiple organisations, however, which requires manually adding them to a JSON secret in AWS Parameter Store with a mapping of their email address and the organisations for whom they will be submitting monitoring reports.

### Delta

While not a Funding Service built service, Delta's authentication methods are useful to consider. Delta uses the OAuth 2 Authorization Code flow which allows them to use a standard OAuth client library in Delta. Unauthenticated users are redirected to its own auth service and shown a login page where they can provide a username and password as a standard form submission, or with Single Sign On (SSO) through Azure AD.

For more on Delta's authentication method, [read their README guidance](https://github.com/communitiesuk/delta-auth-service/tree/main/auth-service#oauth-flow).


## What are the problems with the current state?

Authentication for the current services involves a number of long, error-prone manual processes and is a recurring pain point for users, frequently coming up as an issue in service desk support tickets ([see examples on Confluence](https://mhclgdigital.atlassian.net/wiki/spaces/FS/pages/569344026/Qualitative+Support+ticket+analysis+for+February+28th+-+May+30th+2025#6.4-Authentication-log-in)).

- The manual process of adding users to Azure AD Security Groups is long-winded and error prone, with the lists often incomplete and no easy batch process to add users in bulk. An API integration with Azure AD has been investigated but has been blocked by permissions issues.
- All users (including guest users) in our Azure AD are required to use Multi-Factor Authentication (MFA) when authenticating. For users of Submit, changing their MFA device or losing it often results in them not being able to authenticate, and a request has to be made to our MHCLG IT team to reset it, along with verification that the request is legitimate. All of this takes time and is a process outside of Funding Service's control.
- There is also regular confusion about the link to the Submit service, with users authenticating via Azure AD and expecting it to be present in the Microsoft 'Apps' window rather than then going directly to the service URL.
- Use of the federated Azure AD authentication and light-touch email domain mapping for permissions is also brittle on the Submit service, with new users needing to be added to the relevant Azure AD Security Groups for each monitoring round, and users who need to submit returns for multiple local authorities needing to be manually added to a secrets JSON in AWS which grants additional permissions.
- In Assess, the need to add user emails to specific Azure AD Security Groups for each new grant (and the setting up of these security groups in the first place) is a long and manual process. Tying permissions to these groups also leads to issues on non-production environments when needing to test grants at different permission levels in end to end tests using the same email addresses leads to issue with the basic authentication sidecar protecting these environments, as the sheer number of roles returned causes issues (see the [Jira ticket documenting this issue](https://mhclgdigital.atlassian.net/browse/FLS-1433)).

## What authentication methods are we implementing for MVP?

We are not proposing radically different authentication methods for Access or Deliver Grant Funding, but rather looking to solve or avoid the issues listed above.

### Deliver Grant Funding

We will use federated authentication via MHCLG's Azure AD tenant to control access to Deliver Grant Funding. This part of the service is the administration interface for internal users, all of whom will have existing @communities.gov.uk email addresses or, in the case of future Assessors, be familiar with authenticating via Microsoft and will likely already be guest users in Azure AD.

With one exception, we are not proposing using Azure AD Security Groups to sync or manage permission groups, as this very manual process has proven to be a pain point for Funding Service when onboarding grants or setting up monitoring reports. Instead, Role Based Access Control is controlled by the database in the application ([read the recent authorisation ADR](https://github.com/communitiesuk/funding-service-requests-for-comments/blob/main/adr/2025-05028-authorisation-model.md) for more on how we propose to manage permissions within Access and Deliver Grant Funding).

The one exception is the pre-existing `FSD_ADMIN` Security Group, whose members include most of the Funding Service. This group will be used to identify SSO users who should have Funding Service Admin permissions within the platform when they sign in, and will be kept as the single source of truth. In future we may need to split this group further, into Funding Service form designers and Funding Service platform admins (developers) should the permissions need more granularity or should we need to restrict certain admin actions to an even smaller group. This should not be a difficult issue to resolve should this need arise, however, and we could split the existing small security group into two, or manage the form designer permissions within the service.

Using federated authentication has the benefit of being secure, robust, and something that all internal users will be familiar with. Users are also mandated to use Multi-Factor Authentication (MFA), which adds an additional layer of security.

#### Other government departments

The ideal solution for users from other government departments authenticating to Deliver Grant Funding would be cross-tenant access from their own deparment's Azure AD tenant, but this is not currently being supported by our IT team.

Other digital teams in MHCLG, including Delta, Homes for Ukraine and the Local Government Outcomes Framework (LGOF), are also looking at the issue of giving access easily to users from other government departments (see [Jira ticket discussing this with the LGOF team](https://mhclgdigital.atlassian.net/browse/FSPT-426)). Until this kind of cross-tenant access becomes a viable option, the most appropriate solution remains adding OGD users to the MHCLG Azure AD tenant as guest users.

### Access Grant Funding

Grant applicants and recipients will use magic links to authenticate for Access Grant Funding. For MVP, they will likely be sent a link to a grant's monitoring collection, where they can request a magic link sent to their email to authenticate and access a session to complete the report.

Unlike the current magic link journey in Apply, which doesn't include any kind of role or permissions modelling, Role Based Access Control for Access Grant Funding will be managed in the platform and while we expect the first monitoring collections to involve some manual adding of expected Access Grant Funding users to organisations in order to complete their reports the expectation is that in future this would become more self service, with some Local Authority admin users having permissions to add other users rather than it being a task to be completed by Funding Service.

We also plan for monitoring reports to be attached to an organisation rather than an individual user which will allow Access Grant Funding users to collaborate on completing a monitoring report. This will also solve the problem of users who need to complete monitoring reports on behalf of a number of Local Authorities, as they can be added to specific grant monitoring reports by the Local Authority admins rather than this request needing to come through Funding Service.

### Delta

The one additional authentication method we are considering and may be scoped in for MVP is federated authentication through Delta, specifically for Section 151 Officers.

Delta already has a large user base who will be familiar with its authentication flow, and it already includes user roles/permission for Section 151 Officers or users who have delegated Section 151 Officer permissions. In order to make their report sign-off experience on Access Grant Funding smoother we are considering allowing Section 151 Officers to authenticate via Delta.

This would give us assurance that the Section 151 Officer is the right person, and cut down on the number of services the Section 151 Officers will need to sign in to.

Delta is set up to allow federated authentication, but on discussion with the Delta team the information that is passed back in the SAML token does not include Section 151 Role information. Implementing authentication via Delta would therefore include some developer work on the Delta side in order to include this information in the token.

See [the Jira ticket for this spike work](https://mhclgdigital.atlassian.net/browse/FSPT-425) for more detail, and a [write-up of the initial conversations with the Delta team](https://mhclg.sharepoint.com/:fl:/g/contentstorage/CSP_283061c0-d391-4acb-b480-1af97f9bdccd/EfWVfJx90W5InC5abU09UEABjYC7sUc8sVW4GlIJydsxsQ?e=mBly1H&nav=cz0lMkZjb250ZW50c3RvcmFnZSUyRkNTUF8yODMwNjFjMC1kMzkxLTRhY2ItYjQ4MC0xYWY5N2Y5YmRjY2QmZD1iJTIxd0dFd0tKSFR5MHEwZ0JyNWY1dmN6Umx4Rl9MSVhQNUh1Y2k4UGdnMnEyd1hyQjZwM29wcVNLRDVTakcxRWxHYyZmPTAxWUpRQ1FZN1ZTVjZKWTdPUk5aRUpZTFMyTlZHVDJVQ0EmYz0lMkYmYT1Mb29wQXBwJnA9JTQwZmx1aWR4JTJGbG9vcC1wYWdlLWNvbnRhaW5lciZ4PSU3QiUyMnclMjIlM0ElMjJUMFJUVUh4dGFHTnNaeTV6YUdGeVpYQnZhVzUwTG1OdmJYeGlJWGRIUlhkTFNraFVlVEJ4TUdkQ2NqVm1OWFpqZWxKc2VFWmZURWxZVURWSWRXTnBPRkJuWnpKeE1uZFlja0kyY0ROdmNIRlRTMFExVTJwSE1VVnNSMk44TURGWlNsRkRVVmsyTjB0QlIwZERRMVEyVFVaRVdWWlNTVUpLTWtOYVdFWkdOdyUzRCUzRCUyMiUyQyUyMmklMjIlM0ElMjJkYzczOTYwOS0wZTFjLTRlMWQtYjRiNi1kOTZiMmQ4ODBhMWMlMjIlN0Q%3D).

## Architectural diagram for MVP

![Access and Deliver Grant Funding Architectural Diagram](https://github.com/user-attachments/assets/ee9ec483-ec99-4309-b0a3-05b11897e199)

## What alternatives are we proposing to investigate further in future?

### OneLogin

We considered using GOV.UK One Login, but given the users are primarily B2B users (eg. 3rd sector organisations and Local Authorities) it is unclear how well suited One Login is to this use-case.

It is something we could consider in future and we want to reach out to other digital teams using One Login to find out if any of them have a simialr B2B use case as we do, and how their implementation of One Login has worked for them.

## What are the key risks to manage or mitigate?

* **Security risks** - Owning the login page ourselves there are still some security risks that we will have to own, such as risks of exploitation, DOS, SQL injection, MFA authentication vulnerabilities etc. This is something we will have to continue to mitigate against.
* **Magic link security** - On the current services there were some security incidents as a result of the implementation of magic links. While we have no externally exposed API endpoints or documentation that could be exploited in a similar way to these incidents, it's something we will have to continue to be mindful of and to mitigate against.
* **Single points of failure** - If there are outages with any federated authentication providers (Microsoft or MHCLG's Azure AD tenant, or Delta) then these will need to be accounted for in the general running of the service.
* **Compromised accounts** - The risk of the SSO account being compromised and therefore having access to the system is a also something we will have to consider, though relying on robust platforms such as Microsoft which enfore MFA should reduce this risk (and it's worth noting creating the login flow and managing authentication directly ourselves would likely still not be as secure as federating via Microsoft). Controlling role-based access permissions within the service and enforcing the principle of least privilege should also mitigate against this risk.
* **Federation misconfiguration** - we will also have to mitigate against misconfiguration of any of the federated authentication methods. Controlling role based access within the service itself rather than via federated groups or policies should help avoid security loopholes, but we will have to be mindful of this risk when configuring federated authentication methods.
