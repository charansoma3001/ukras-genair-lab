# Task 3 - Hands

## Goal

Give the robot hands: open containers, place objects, toggle appliances, slice,
cook - the INTERACT functions.

## Add abilities

From [the API](../api-reference.md), for example:

```text
open(object_id) : Open a cabinet, fridge or drawer.
close(object_id) : Close an open container.
place_on(receptacle_id) : Put the held object onto/into something.
toggle_on(object_id) : Turn something on.
slice(object_id) : Slice something.
```

## Try this

- *"Put the apple in the fridge"* - needs navigate -> open -> pickup -> place.
- *"Slice the bread"* -
- *"Chop the bread"* - does the robot know what "chop" means?
- *"Pick up the apple"*  and then  *"Pick up the bread"* - can it do both? What happens when hands are full and can you fix this?

## Note

Most actions need the robot to be close to the target and looking at it. If an
action fails, read the error in the step log; it usually says why.
