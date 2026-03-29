def validate_triangle(side_one: int, side_two: int, side_three: int) -> bool:
    """Validate if a triangle is valid."""
    return side_one + side_two >= side_three or side_one + side_three >= side_two or side_two + side_three >= side_one


def type_triangle(side_one: int, side_two: int, side_three: int) -> str:
    """Return the type of triangle."""
    if side_one == side_two == side_three:
        return "EQUILATERAL"
    elif side_one == side_two or side_one == side_three or side_two == side_three:
        return "ISOSCELES"
    else:
        return "SCALENE"
