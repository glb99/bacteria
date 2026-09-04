# Raw article — What Is Domain Driven Design (DDD)? (Mert Özler)

> Retrieved via r.jina.ai reader (Medium blocks direct fetch). Text verbatim; images not captured — image captions remain as stray lines.

Title: What Is Domain Driven Design (DDD)?

URL Source: https://meozler.medium.com/what-is-domain-driven-design-ddd-a9a0b9832543

Published Time: 2024-04-24T06:30:42Z

Markdown Content:
[![Image 1: Mert Özler](https://miro.medium.com/v2/resize:fill:64:64/1*kgIVL88_xIQjAEroTWWeVg.jpeg)](https://meozler.medium.com/?source=post_page---byline--a9a0b9832543---------------------------------------)

10 min read

Apr 24, 2024

--

Eric Evans, Domain-Driven Design

My aim in this article is to discuss what Eric Evans introduced in 2003, which is Domain Driven Design, a widely accepted concept in the industry, and how it can be applied. Most of the sources in this article are taken from Vaughn Vernon’s book ‘**Domain Driven Design Distilled**’. I recommend this book for a deeper understanding.

In short, DDD primarily involves modeling Bounded Context with Ubiquitous Language. Yes, when we phrase it like this, it might not make much sense. Let’s explain these concepts further in the rest of the article.

DDD is a set of tools that helps us design and implement software that provides high value both strategically and tactically. With DDD, strategic development tools enable developers and teams to make the best software design choices and implementation decisions in terms of competitiveness for the business.

Strategic Design & Tactical Design

## Strategic Design

In DDD, if we don’t start with Strategic Design and understand it well, it’s not possible to effectively implement Tactical Design. Therefore, to understand DDD, we should start with Strategic Design.

Before delving into the depths of Strategic Design, let’s briefly explain the concepts of B**ounded Context** and **Ubiquitous Language** that we will use while understanding DDD.

### What is Bounded Context?

Here, there are two distinct Bounded Contexts. Later on, we will see how to relate these two different Bounded Contexts using Context Mapping.

The domain is divided into specific contexts, with each context having its boundaries. A complex domain can be divided into subdomains within itself.

### **What is Ubiquitous Language?**

It emphasizes that the visual Ubiquitous Language emerges through the collaboration of Domain Experts and developers

It ensures the existence of a shared language between business and developer teams. Business concepts and processes have a direct place in the software. It directly influences the software design and code.

It aims for every action in the business to have a corresponding function in the software, and for each member of the team (both business and developers) to have a clear understanding whenever these functions/concepts are mentioned. All structures within the domain serve this purpose.

DDD is all about modeling your domain quite explicitly. Using Domain Events enables both clear modeling and sharing of events with systems that need to know what’s happening. Here, the relevant parties can be local Bounded Contexts or remote Bounded Contexts.

Bounded Context is essentially a semantic boundary. This means that within the boundaries of software projects, each component has a specific meaning.

When Bounded Context is developed as a significant strategic initiative of the company, it is called the **Core Domain**.

When considering the role of language in a software model, think of the various nations that make up Europe. In any country within this area, each nation has its own distinct and official language. For example, countries like Germany, France, and Italy have designated official languages within their borders. When you cross a border, the official language changes. You can think of Bounded Contexts in a very similar way to language boundaries. In DDD, _languages are the languages spoken by the team that owns the software model, and a significant written language is the source code of the software model._

A team can work with multiple Bounded Contexts, but multiple teams should not work on a single Bounded Context. For each Bounded Context, we should cleanly separate the source code and database schema according to the Ubiquitous Language. Acceptance tests and unit tests should be kept alongside the main source code.

### The Fundamentals of Strategic Design

We need at least two fundamental Strategic Design tools. One of them is Bounded Context, and the other is Ubiquitous Language. Bounded Context should encompass the core concepts of the strategic initiative and exclude those outside of it.

Domain Experts naturally focus more on business-related topics. Their thoughts are based on their vision of how the business operates.

Developers may be focused on programming languages and the technologies they use. However, it’s crucial for developers working on a DDD project to avoid being overly technical to the point where they cannot see the business focus of the core strategic initiative. In other words, in a DDD project, developers prioritize the business over technical issues. This allows developers to gradually embrace the Ubiquitous Language evolving naturally within their Bounded Contexts.

### Focus on Business Complexity, Not Technical Complexity

Remember, the primary reason we use DDD is for business complexity. Therefore, we never want to make the domain model more complex than it needs to be. DDD primarily aims to make business complexity understandable and manageable. Developers should look at the business model with Domain Experts because of this.

Both developers and Domain Experts should avoid the tendency for documents to speak for them. The best Ubiquitous Language will emerge in a feedback loop that creates a united mental model within the team. Open communication, exploration, and challenges enable the team to gain more knowledge about the Core Domain.

Don’t leave the Core Domain to be named only by names; that is, the Core Domain should not be limited to just the names of your functions and Domain Models. Instead, scenarioize the Core Domain based on what the business model requires.

### What is Subdomain?

In short, a Subdomain is a subset of the general business domain.

When using DDD, a Bounded Context should align one-to-one (1:1) with a single Subdomain. This means that when using DDD, if there is a Bounded Context, there is a corresponding subdomain targeted within that Bounded Context.

### What is Context Mapping?

Context Mapping is the mapping of two Bounded Contexts in some way.

There are two Ubiquitous Languages ​​in two Bounded Contexts, and there are various methods for applying Context Mapping. We will briefly touch on these methods shortly. Before that, let’s explain why Context Mapping is necessary with an analogy.

Imagine two teams needing to work together but operating beyond national borders and unable to speak the same language. Either the teams would need an interpreter, or one or both teams would need to learn the other’s language to a significant extent. Finding an interpreter would be less work for both teams, but it could be costly in various ways. Consider the extra time one team spends communicating through an interpreter, then the time it takes for the interpreter to convey the expressions to the other team. It may work for the first few moments, but it becomes cumbersome afterward. Still, teams may find it a better solution than learning and adopting a foreign language and constantly switching between languages. Of course, this only describes the relationship between two teams. What if several other teams are involved? Similarly, the same trade-offs would apply when translating one Ubiquitous Language to another or accommodating another Ubiquitous Language.

Now let’s examine the types of Context Mapping together.

**Partnership:** There is a Partnership relationship between two teams. Each team is responsible for a Bounded Context. They form a partnership to align the dependent sets of goals of the two teams.

**Shared Kernel:** Teams must agree on the models to be shared. It’s possible that only one team can maintain the shared code, structure, and tests. Shared Kernel can be very difficult to initially conceptualize and challenging to maintain because there needs to be clear communication between teams and a continuous agreement on what model to share.

**Customer-Supplier:** Customer-Supplier defines a relationship between two Bounded Contexts where the Supplier is upstream and the Customer is downstream, and their respective teams. The Supplier holds sway in this relationship and is responsible for providing what the Customer needs.

**Conformist:** A Conformist relationship arises in situations where there are upstream and downstream teams, and the upstream team lacks the motivation to support the specific needs of the downstream team.

**Anticorruption Layer**: Anticorruption Layer is the most defensive Context Mapping relationship; downstream teams create a translation layer between their own Ubiquitous Language and that of the upstream teams. This layer isolates the downstream model from the upstream model and translates between the two.

**Open Host Service:** Open Host Service defines a protocol or interface that makes the Bounded Context accessible as a set of services. The protocol is “open” for relatively easy use by anyone who needs to integrate with the Bounded Context.

**Published Language:** Published Language is a well-documented information exchange language that can be used by any number of consumer Bounded Contexts by providing simple consumption and translation.

**Separate Ways:** Separate Ways defines a situation where integration with one or more Bounded Contexts cannot provide significant returns through various Ubiquitous Language consumption paths.

So far, we’ve summarized the fundamentals of Strategic Design in DDD. Now that we’ve laid our foundation, let’s delve into the fundamentals of Tactical Design in DDD.

## Tactical Design

Just like in Strategic Design, there are specific concepts unique to Tactical Design. Let’s briefly explain these concepts as we understand Tactical Design.

### What is Entity?

An Entity models an individual thing. Each Entity has a unique identity (such as an ID) that distinguishes it from all other Entities of the same or different types. Most of the time, an Entity will be mutable, meaning its state will change over time.

### What is Aggregate?

Each Aggregate consists of one or more Entities, and this set of Entities is called the Aggregate Root. Additionally, there may be Value Objects created on Aggregates.

### What is Value Objects?

A Value Object, or simply a Value, models an immutable conceptual whole. Within the model, a Value is just a value. It doesn’t have a unique identity like an Entity, and equality is determined by comparing the attributes encapsulated by the Value type.

Additionally, a Value Object is not an object but is often used to represent, quantify, or measure an Entity. Each Aggregate forms a transaction consistency boundary.

This means that when a transaction controlled within a single Aggregate is sent to the database, all component parts must be consistent according to business rules.

### What is Domain Event?

Domain Event is the recording of a business event that occurred within the Bounded Context (e.g., ProductCreated, OrderCreated). Domain Events are crucial tools for Strategic Design.

An example Domain Event table in DDD.

You must pay attention to how you name Domain Event types. The names used should reflect the Ubiquitous Language of the model. These words will serve as a bridge between the events occurring in the model and the outside world.

It is crucial to communicate Domain Events effectively. Domain Event type names should express a past event, meaning they should be a past-tense verb.

It is important to save both a modified Aggregate and its corresponding Domain Event within the same transaction. If an object-relational mapping tool is used, you would save the Aggregate to a table and the Domain Event to an event store table, and then complete the operation. If Event Sourcing is used, the state of the Aggregate is entirely represented by Domain Events.

To save both the Aggregate and the Domain Event within the same transaction, you can use the Outbox Pattern.

After saving your Domain Event to the event store table, it can be published/produced to anyone interested. This can be within your own Bounded Context or to external Bounded Contexts. It’s a way of notifying the outside world that a significant event has occurred in your Core Domain.

For example, consider an e-commerce domain: I’m notifying that a customer has purchased a product with the OrderCreated event. As a result, the shipping process should begin, and the relevant domain can apply its own business rules after consuming this event.

### What is Event Sourcing?

Event Sourcing can be defined as the practice of recording all Domain Events that occur for an instance of an Aggregate, serving as a record of what has changed in that Aggregate and what actions have been taken.

The event store is a sequential storage collection or table where all Domain Events are appended. The append-only nature of the event store speeds up the storage mechanism, hence, we can assume that a Core Domain using Event Sourcing would have very high throughput, low latency, and high scalability.

We’ve examined the fundamentals and concepts of Strategic Design and Tactical Design used in DDD so far. Before concluding the article, I will briefly discuss Event Storming.

### What is Event Storming?

Event Storming is a rapid design technique aimed at involving both Domain Experts and developers in a quick learning process. It focuses on business events and processes rather than names and data.

In an Event Storming session, all team members involved in creating the Ubiquitous Language come together to model the business in the Domain. It is usually implemented by placing sticky notes on a large wall and a whiteboard, but it doesn’t necessarily have to be done face-to-face.

If you want to see how Event Storming is applied in more detail, you can check out an example session conducted by the Trendyol team from [here](https://www.youtube.com/watch?v=sxU11Qyx8cQ).
