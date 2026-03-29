# -*- coding: utf-8 -*-
import logging

from sample.helpers import helpers


def get_type_triangle(side_one: int, side_two: int, side_three: int):
    """Uses helpers support methods to get the type of triangle."""
    if helpers.validate_triangle(side_one, side_two, side_three):
        logging.debug("Valid triangle!")
        return helpers.type_triangle(side_one, side_two, side_three)
    logging.error("Not a valid triangle!")
    return "ERROR!!"
