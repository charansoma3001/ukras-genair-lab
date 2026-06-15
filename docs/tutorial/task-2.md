# Task 2 - Navigation

## Goal

Give the robot the ability to move and look around, so it can reach objects that
aren't already in front of it.

## Add abilities

From [the API](../api-reference.md), equip some MOVE functions, for example:

```text
rotate_left(degrees) : Turn to the left.
rotate_right(degrees) : Turn to the right.
look_down() : Tilt the camera down.
look_up() : Tilt the camera up.
```

## Try this

- A command that needs the robot to turn around or look down to find a target.
- Compare behaviour with and without the movement abilities equipped.

## Prompt ideas

Tell the robot, in the system prompt, *when* to navigate or look before acting.
