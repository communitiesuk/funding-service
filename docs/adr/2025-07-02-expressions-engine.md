```
Title: 'Expressions' in funding service forms
Owner: Samuel Williams

Collaborator(s): Platform Team
Created on: 2025-07-02
Status: Final
Finalised on:
```

## Overview

The Funding Service has decided to take on the responsibility for form building through its own service, rather than using some commercial off-the-shelf (COTS) software. This is because form building has been an extreme pain point for us since the service was built, and the available options do not seem to allow us to move with enough velocity and reliability. It's a controversial and significant decision to build our own thing, but we have reasonable confidence that it will result in a better outcome in the long run. When building forms, we need the ability to validate user input and route users to various questions in an easy-but-flexible way. This ADR covers the settled implementation for the Funding Service's "expressions engine", which powers conditions, validation, and personalisation of forms.

## What is the current state?

The expressions engine is a novel implementation for the new funding-service app, so there is limited strictly-current state to compare against. However, there are adjacent parts of MHCLG's and Funding Service's technical estate that achieve similar things to the 'expressions engine' we have built:

### Delta

Delta's form builder and runner is built on [Orbeon Forms](https://www.orbeon.com/). It is extremely powerful and extensible, letting you write essentially any validation logic you want using [XPath expressions](https://doc.orbeon.com/xforms/xpath). MHCLG and the Funding Service does not have many people knowledgeable in this DSL, and has dedicated Orbeon Form Engineers to help abstract the complexity of this from the majority of people using Delta for forms. This can be a bottleneck for the service, leading to stress and undue pressure both on the Orbeon Engineers, the service, and the department.

This is extremely flexible and allows almost any validation expression imaginable to be represented, but at the cost of needing a high level of skill and knowledge to do it quickly, successfully, and reliably.

### [XGovFormBuilder](https://github.com/XGovFormBuilder/digital-form-builder) / Form Designer

XGovFormBuilder takes a WYSIWIG/visual design approach to form builder, with a canvas that you can drop pages onto and links between them to describe the journey through the form.

Conditions can be added on links between pages. Each form field you've added has a set of available condition types (eg 'starts with', 'ends with', 'contains') and the user interface will let you build these out. Specific kinds of validation can be added to each form field, based on the field type. If you need to set conditional rules or add validation beyond those that the software supports, a code change needs to happen to add support for it specifically. It isn't possible to write generic conditions/validation rules.

## Why are we changing?

The existing options do not meet our current or anticipated future needs with the level of reliability and speed that we're after. With a few years of knowledge and experience of the needs under our belt, we believe that we need the simplicity of managed expressions and the flexibility of custom expressions in unison. Neither of the current options support this in a way that works for our service at the moment.

## How does the expressions engine work?

The implemented, currently living mainly in [app/common/expressions/__init__.py](https://github.com/communitiesuk/funding-service/blob/main/app/common/expressions/__init__.py), aimed to address the following ideas:

- Flexible and able to evaluate almost any imaginable condition
- Simple to use and understand, for both form designers and developers

Funding Service developers work mainly in Python, so writing something Python-esque should be very approachable. Form designers should not be expected to know a complex language and should be able to use a simple user interface to design the vast majority of what they need.

For writing the expressions, we've therefore decided to use a subset of the standard Python language, evaluated using the `simpleeval` library. Using raw `eval` is an option but comes with a vast array of security concerns, and given that we will be processing user input, it is vital that we have a high level of trust in the security posture we're taking when evaluating the expressions. `eval` is off the table. `simpleeval` works by reading the expression and converting it to a Python Abstract Syntax Tree (AST), and then running that through an allowlisted evaluator that only allows a very small subset of the Python language. It also evaluates the expression with a limited context (set of variables), meaning that the data the expression has access to can be defined very clearly and precisely.

### Context
The context for an expression is the sum of data available for it to query. We can build the context for an expression based on the user interacting with the system, so that they can have a personalised experience. Some examples of context are:

- all of the answers in their current submission
- their organisation
- the grant they're reporting on
- the projects their organisation is working on under the approved funding

This can be as limited or as broad as we need it to be, with some small consideration for memory constraints and performance. Having the ability to inject very flexible context for expressions will allow us to use it across the entire platform. It takes advantage of having all of the funding data in one place, to provide a good user experience for both form designers, grant recipients, and grant teams.

### What are expressions?

An expression might look like any of these:

- `1 + 1`
- `answer == 'yes'`
- `answer < 50`

Or something more complex like:

- `answer not in ['red', 'blue', 'green'] and last_reporting_round.colour == 'yellow'`

These should all be intuitive to read and write as a Funding Service developer.

We believe that form designers will generally be using a very standard set of expressions, and are choosing to present them a user interface that exposes a set of so-called "Managed expressions". These might be things like "Greater than", "Less than", "Between" for a numeric field. The user interface will let them choose these in a radios-type question, and then provide further information through standard form fields. When the form designer has filled the information in, we will convert that to an expression like `answer >= 0 and answer <= 100` and store that on their behalf. A form designer should not need to understand or even be aware of the existence of the expressions language unless they are doing some extremely complex validation or branching. In that case, we might allow them to learn about the expressions engine, or they might still need to work in tandem with any Funding Service developer.

The expression engine is currently aimed at supporting three key features: validation, conditions, and personalisation. We believe that all three of these key concepts can be supported through a single expressions framework, and that by doing so it greatly reduces the amount of technical work required, and the complexity of the system. A suitably flexible and generic expressions language should be able to grow to meet any future needs of the funding service around applying constraints or personalisation. We believe this provides a strong, simple, and extensible foundation for the platform.

### Validation

For validation, the expressions engine is invoked with data that the user is currently submitting. For example, for the question "How much did you spend last year?", you might want to validate that the answer is positive, so we could apply a Managed expression of "Greater than £0", which translates to an expression statement of something like `answer > 0`.

Currently, validation can only target the *current* answer being submitted, but we expect in the near-to-mid-term to allow a wider set of context. For example, you might validate that the answer to this question is greater than the answer to _some previous_ question.

### Conditions

Conditions apply to questions and determine whether or not the user should see that question. For example, you might first ask the question "How much did you spend last year?". If the user says they spent more than £1,000,000, the form designer may wish to ask a follow-up question asking them to justify the spend. A condition such as `q_how_much_did_you_spend > 1_000_000` could be applied to this question. If the condition evaluates to `true`, then the question would be shown. Otherwise it would not.

### Personalisation

In order to reduce duplication and increase reliability, we anticipate the need for some questions to include information dynamically, based on the context of the user providing the data. For example, we might want a question to read `What role do you have in {{ organisation name }}?`. This needs to be different for each user, so that someone from Bolton Council might see "What role do you have in Bolton Council?".

Therefore we need a way to inject personalised information into things like question text, hint text, section names, validation messages, and more.

The expressions engine has access to contextual data based on the user and the platform, so it should be able to pull from this reliably to inject that information into templated text messages.

## Who will be affected and how?

### Form designers
Form designers currently have to use a mix of Delta and XGovFormBuilder. When needing to do complex validation or conditional logic, it is often required to hand over to an Orbeon Engineer because the system is not feasible to be used by non-technical people.

We have a good level of confidence that this new system should allow form designers to be much more in control of building forms themselves without the need for involving technical staff, which should allow the Funding Service to deliver more quickly and reliably.

### Funding Service developers
Funding Service developers have, on rare occassions, been asked to learn and work with Delta's XPath expressions language. This takes some time to upskill into, even for relatively simple asks. If we are able to start servicing the majority of Funding collections using the new service, and the new expressions engine, it should reduce the need for developers to work directly on form building. In the cases they do need to, it should be far easier for them to do the work.

## What are the key risks to manage or mitigate?

### Security of the expressions engine

The idea of allowing users to enter arbitrary code-like input which will then be evaluated by the system should set off alarm bells for developers everywhere. We believe we have been appropriately cautious and conscientious in the implementation to mitigate or eliminate the risk of serious vulnerabilities, but this should be a key ongoing consideration. A set of tests have been written to ensure that some key expected attack ideas are not available, but this will remain one of the more interesting areas for any potential attackers.

The limited subset of Python available to the expressions engine at the time of writing is effectively:

- raw data (hard-coded numbers, strings, lists, etc)
- variable definitions, which must line up with context provided to the expression
- attribute and item lookup on variables (`variable.item`, `variable['item']`), to allow pulling data from rich/nested data
- basic operations like addition, subtraction, multiplication, etc.

### Future needs

We anticipate some future needs that are not met by the current simple implementation, such as applying aggregations over datasets. For example, we might want to sum up all of the amounts of money declared as spent during a grant recipient's last 5 monitoring reports. An expression for this might look like `sum(reports[*].amount_spent)`. The `[*]` syntax is not valid Python and intended just to represent 'all historical reports'. We will need to work out how to support these kind of aggregate functions when we approach them. If the expressions engine or Python language ends up feeling insufficient to meet this, or other future needs, we will need to deal with that.

I have reasonably confidence currently that the above example, and others, should be possible to support. If we cannot use bog standard Python, then we may need to start introducing some DSL elements, which could introduce complexity and unpredictability for Funding Service developers writing custom expressions.
