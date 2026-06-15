# Task 1 - First commands

## Goal

Get a feel for the loop: type a command, watch the robot pick one ability at a
time, and see where it succeeds or gets confused.

## What you start with

The default abilities equip a minimal set:

```text
navigate_to(object_id) : Walk over to an object so you can reach it.
pickup(object_id) : Pick up a visible object.
get_object_metadata(object_id) : Check the exact state of one object.
finish(message) : Say the command is complete.
```

## Try this

- Ask *"what do you see?"* and *"pick up the apple"*.
- Watch the step log: which ability does it choose, and why?
- Find a command it gets wrong - that's what Tasks 2 and 3 fix.

## Where the fix lives

If the robot misunderstands *intent*, edit the **System Prompt**. If it
physically *can't* do something, it's missing an ability - see
[the API](../api-reference.md).
